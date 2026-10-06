"""Loopback-only HTTP server with origin and CSRF checks; stdlib only."""
import argparse
import json
import math
import mimetypes
import secrets
import threading
import time
import webbrowser
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit
from engine import World
from ollama_client import OllamaClient,validate_profile

ROOT=Path(__file__).resolve().parent

class Game:
    def __init__(self,seed=42):
        self.world=World(seed); self.lock=threading.RLock(); self.token=secrets.token_urlsafe(32)
        self.speed=1.; self.stop=threading.Event(); self.generation=0; self.last_ai_tick=-100; self.pending_law=None
        self.client=OllamaClient()
    def start_workers(self):
        threading.Thread(target=self.sim_loop,daemon=True).start(); threading.Thread(target=self.ai_loop,daemon=True).start()
    def sim_loop(self):
        while not self.stop.wait(.5/max(.25,self.speed)):
            with self.lock: self.world.step()
    def ai_loop(self):
        while not self.stop.wait(1):
            with self.lock:
                if not self.world.ai_enabled: continue
                generation=self.generation; snapshot=self.world.snapshot(); law_job=self.pending_law
                if law_job:
                    self.pending_law=None; self.world.ai_status='Entwurf wird vom Modell ausgelegt ...'
                elif not self.world.running or self.world.phase!='debatte' or self.world.tick-self.last_ai_tick<16: continue
                else:
                    self.last_ai_tick=self.world.tick; self.world.ai_status='Eine Figur denkt ... (Simulation läuft weiter)'
            try:
                if law_job: result=validate_profile(self.client.interpret(snapshot),snapshot['parties'])
                else: result=self.client.decide(snapshot)
                with self.lock:
                    if generation!=self.generation or not self.world.ai_enabled: continue
                    if law_job:
                        # Only replace interpretation before amendments/votes for that exact law.
                        if self.world.law==snapshot['law'] and self.world.phase=='debatte' and result:
                            self.world.law_profile=result; self.world.ai_status='Entwurf ausgelegt und geprüft'
                            self.world.log('interpretation','Modell-Auslegung für den Entwurf liegt vor.',[],'Geprüfte begrenzte Spielwirkungen',5,data=result)
                        else: self.world.ai_status='Auslegung verworfen: Entwurf/Phase geändert oder ungültige Antwort'
                    else:
                        applied=self.world.apply_proposal(result)
                        self.world.ai_status='Modellentscheidung angewendet' if applied else 'Veraltete/ungültige Modellentscheidung verworfen'
            except Exception:
                with self.lock:
                    if generation==self.generation: self.world.ai_status='Ollama nicht erreichbar/Antwort ungültig; Regelmodell übernimmt'
                self.stop.wait(10)
    def control(self,p):
        action=p.get('action')
        with self.lock:
            w=self.world
            if action=='run': w.running=True
            elif action=='pause': w.running=False
            elif action=='step':
                was=w.running; w.running=True; w.step(); w.running=was
            elif action=='reset':
                seed=p.get('seed',42)
                if type(seed) is not int or not 0<=seed<=2**32: raise ValueError('Seed ungültig')
                self.world=World(seed); self.generation+=1; self.pending_law=None; self.last_ai_tick=-100
            elif action=='law':
                w.set_law(p.get('text','')); self.generation+=1
                if w.ai_enabled: self.pending_law=w.law
            elif action=='settings':
                speed=p.get('speed',self.speed); absurdity=p.get('absurdity',w.absurdity); chaos=p.get('chaos',w.chaos)
                if any(type(x) not in (int,float) or not math.isfinite(x) for x in (speed,absurdity,chaos)): raise ValueError('Einstellung ungültig')
                if not .25<=speed<=8 or not 0<=absurdity<=100 or not .1<=chaos<=3: raise ValueError('Einstellung außerhalb des Bereichs')
                self.speed=speed; w.absurdity=absurdity; w.chaos=chaos
                if 'ai' in p:
                    if type(p['ai']) is not bool: raise ValueError('KI-Einstellung ungültig')
                    w.ai_enabled=p['ai']; w.ai_status='Ollama aktiv; Anfragen laufen nebenher' if p['ai'] else 'Aus: Regelmodell übernimmt'
                    if p['ai']: self.pending_law=w.law
            elif action=='intervene':
                if p.get('sandbox') is not True: raise ValueError('Sandbox nicht aktiviert')
                if not w.intervene(p.get('kind'),p.get('actor'),p.get('target')): raise ValueError('Aktion aktuell nicht möglich')
            elif action=='load':
                self.world=World.load(p.get('save')); self.generation+=1; self.pending_law=None; self.last_ai_tick=-100
            else: raise ValueError('Unbekannte Aktion')
            return self.world.snapshot()

class Handler(BaseHTTPRequestHandler):
    server_version='AFFENKAEFIG/7'
    def log_message(self,*args): pass
    def send(self,status,data,kind='application/json; charset=utf-8',download=None):
        body=json.dumps(data,ensure_ascii=False,allow_nan=False).encode() if kind.startswith('application/json') else data
        self.send_response(status); self.send_header('Content-Type',kind); self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'")
        if download: self.send_header('Content-Disposition','attachment; filename='+download)
        self.end_headers(); self.wfile.write(body)
    def allowed(self):
        host=self.headers.get('Host','')
        return host in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}')
    def do_GET(self):
        if not self.allowed(): self.send(403,{'error':'Host nicht erlaubt'}); return
        path=urlsplit(self.path).path
        with self.server.game.lock:
            if path=='/api/state': self.send(200,self.server.game.world.snapshot()); return
            if path=='/api/token': self.send(200,{'token':self.server.game.token}); return
            if path=='/api/save': self.send(200,self.server.game.world.save(),download='AFFENKAEFIG-save.json'); return
            if path=='/api/history': self.send(200,{'events':self.server.game.world.events,'laws':self.server.game.world.laws},download='AFFENKAEFIG-history.json'); return
        filename='index.html' if path=='/' else path.lstrip('/')
        target=(ROOT/filename).resolve()
        if filename not in ('index.html','style.css','game.js') or ROOT not in target.parents or not target.is_file(): self.send(404,{'error':'Nicht gefunden'}); return
        self.send(200,target.read_bytes(),mimetypes.guess_type(str(target))[0] or 'application/octet-stream')
    def do_POST(self):
        if not self.allowed(): self.send(403,{'error':'Host nicht erlaubt'}); return
        origin=self.headers.get('Origin')
        allowed=(f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}')
        if origin and origin not in allowed: self.send(403,{'error':'Origin nicht erlaubt'}); return
        if not secrets.compare_digest(self.headers.get('X-Game-Token',''),self.server.game.token): self.send(403,{'error':'Token fehlt'}); return
        if self.path!='/api/control': self.send(404,{'error':'Nicht gefunden'}); return
        try:
            n=int(self.headers.get('Content-Length','0'))
            if not 1<=n<=2000000: raise ValueError('Anfrage zu groß/leer')
            p=json.loads(self.rfile.read(n),parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Keine unendlichen Zahlen')))
            if not isinstance(p,dict): raise ValueError('JSON-Objekt erwartet')
            self.send(200,self.server.game.control(p))
        except (ValueError,TypeError,KeyError,AttributeError,OverflowError) as e: self.send(400,{'error':str(e)[:300]})
        except Exception: self.send(400,{'error':'Ungültige Anfrage oder inkonsistenter Spielstand'})

class Server(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,address,game): super().__init__(address,Handler); self.game=game

def main():
    parser=argparse.ArgumentParser(description='AFFENKÄFIG: lokales satirisches Parlament')
    parser.add_argument('--port',type=int,default=8766); parser.add_argument('--seed',type=int,default=42); parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args(); game=Game(args.seed)
    try: server=Server(('127.0.0.1',args.port),game)
    except OSError as e: parser.exit(1,f'Port {args.port} nicht verfügbar. Nutze --port 8767. ({e})\n')
    game.start_workers(); url=f'http://127.0.0.1:{server.server_port}'
    print('AFFENKÄFIG läuft:',url,flush=True)
    if not args.no_browser: webbrowser.open(url)
    try: server.serve_forever()
    except KeyboardInterrupt: print('\nSitzung beendet. Spielstand vor dem Schließen im Browser speichern.')
    finally: game.stop.set(); server.server_close()

if __name__=='__main__': main()
