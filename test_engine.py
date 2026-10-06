import copy
import json
import unittest
from engine import World,clamp,affinity
from config import PARTIES
from ollama_client import validate_profile
from server import Game,Server
import threading
import urllib.request
import urllib.error

class EngineTests(unittest.TestCase):
    def setUp(self): self.w=World(42); self.a=self.w.members[0]; self.b=self.w.members[25]
    def test_seats(self): self.assertEqual(self.w.seats(),{'CDU':16,'CSU':4,'AfD':15,'SPD':12,'Bündnis 90/Die Grünen':9,'Die Linke':6,'SSW':1})
    def test_unique(self): self.assertEqual(len({m['name'] for m in self.w.members}),63)
    def test_seed(self): self.assertEqual(self.w.snapshot(),World(42).snapshot())
    def test_other_seed(self): self.assertNotEqual(self.w.members,World(43).members)
    def test_pause(self): self.w.step(); self.assertEqual(self.w.tick,0)
    def test_run(self): self.w.running=True; self.w.step(); self.assertEqual(self.w.tick,1)
    def test_clamp(self): self.assertEqual(clamp(101),100); self.assertEqual(clamp(-1),0)
    def test_affinity(self): self.assertEqual(affinity([100]*7,[-100]*7),0)
    def test_chat(self): self.assertTrue(self.w.act(self.a,'chat',self.b)); self.assertEqual(self.a['state'],'chatting')
    def test_heckle(self): before=self.b['stress']; self.w.act(self.a,'heckle',self.b); self.assertGreater(self.b['stress'],before)
    def test_brawl(self): self.w.act(self.a,'brawl',self.b,True); self.assertEqual(self.a['sanctions'],1); self.assertEqual(self.a['state'],'fighting')
    def test_sanction(self): self.w.act(self.a,'brawl',self.b,True); self.assertFalse(self.w.act(self.a,'chat',self.b))
    def test_protest(self): self.w.act(self.a,'protest'); self.assertTrue(any(m['state']=='protesting' for m in self.w.members))
    def test_walkout(self): self.w.act(self.a,'walkout'); self.assertEqual(self.a['state'],'outside')
    def test_return(self): self.w.act(self.a,'walkout'); self.w.act(self.a,'return'); self.assertEqual(self.a['state'],'seated')
    def test_resign(self): self.w.act(self.a,'resign'); self.assertEqual(sum(self.w.seats().values()),62)
    def test_switch(self): old=self.a['party']; self.w.act(self.a,'switch'); self.assertNotEqual(self.a['party'],old)
    def test_split(self): self.w.act(self.a,'split'); self.assertEqual(len(self.w.parties),8)
    def test_invalid_action(self): self.assertFalse(self.w.act(self.a,'execute_code'))
    def test_no_target(self): self.assertFalse(self.w.act(self.a,'brawl'))
    def test_self_target(self): self.assertFalse(self.w.act(self.a,'chat',self.a))
    def test_speech(self): self.w.act(self.a,'speech'); self.assertEqual(self.w.speaker,self.a['id'])
    def test_one_speaker(self): self.w.act(self.a,'speech'); self.assertFalse(self.w.act(self.b,'speech'))
    def test_speech_ends(self):
        self.w.act(self.a,'speech'); self.w.running=True
        for _ in range(12): self.w.step()
        self.assertNotEqual(self.w.speaker,self.a['id'])
    def test_evacuation(self): self.w.evacuate(); self.assertTrue(all(m['state']=='evacuated' for m in self.w.members))
    def test_reopen(self): self.w.evacuate(); self.w.running=True; [self.w.step() for _ in range(16)]; self.assertEqual(self.w.phase,'debatte')
    def test_election(self): self.w.call_election(); self.w.running=True; [self.w.step() for _ in range(12)]; self.assertEqual(self.w.election,1); self.assertEqual(sum(self.w.seats().values()),63)
    def test_election_restores(self): self.w.act(self.a,'resign'); self.w.finish_election(); self.assertFalse(self.a['resigned'])
    def test_coalition(self): self.w.break_coalition(); self.assertEqual(self.w.coalition,[])
    def test_streaker(self): self.w.streaker(True); self.assertEqual(self.w.effects[-1]['kind'],'streaker')
    def test_absurd(self): self.w.absurd_event(); self.assertIn(self.w.effects[-1]['kind'],('confetti','goose','blackout','coffee'))
    def test_law(self): self.w.set_law('Die AfD soll abgeschafft werden.'); self.assertEqual(self.w.law_profile['operation']['party'],'AfD')
    def test_word_fragment(self): self.assertEqual(self.w.analyse_law('Neue Tische kaufen')['axes'][4],0)
    def test_short_law(self):
        with self.assertRaises(ValueError): self.w.set_law('a')
    def test_blocked_law(self):
        self.w.phase='wahl'
        with self.assertRaises(ValueError): self.w.set_law('Mehr Geld für alle.')
    def test_vote_count(self): self.assertEqual(sum(self.w.vote()['counts'].values()),63)
    def test_absent(self): self.w.act(self.a,'walkout'); self.assertEqual(self.w.vote()['counts']['abwesend'],1)
    def test_quorum(self):
        for m in self.w.members[:40]: self.w.move(m,'outside',[1.1,.8],30)
        self.assertFalse(self.w.vote()['quorum'])
    def test_vote_effects(self):
        for m in self.w.members: m['values']=[100]*7
        self.w.set_law('Klimaschutz fördern'); before=self.w.stats['ecology'];self.w.resolve_vote();self.assertTrue(self.w.votes['passed']);self.assertGreater(self.w.stats['ecology'],before)
    def test_dissolve(self):
        self.w.set_law('Die AfD abschaffen'); self.w.law_profile['axes']=[100]*7
        for m in self.w.members: m['values']=[100]*7
        self.w.resolve_vote(); self.assertNotIn('AfD',self.w.parties); self.assertEqual(self.w.seats()['Fraktionslos'],15)
    def test_amendment_changes_effects(self):
        old=self.w.law_profile['effects']['ecology']; self.w.begin_amendment();self.assertAlmostEqual(self.w.amendment['profile']['effects']['ecology'],old*.65)
    def test_memory(self): self.w.act(self.a,'chat',self.b); self.assertTrue(self.a['memory'])
    def test_save_roundtrip(self):
        self.w.running=True; [self.w.step() for _ in range(80)]; loaded=World.load(json.loads(json.dumps(self.w.save()))); self.assertFalse(loaded.running);self.assertEqual(loaded.members,self.w.members); self.assertEqual(loaded.rng.getstate(),self.w.rng.getstate())
    def test_save_deterministic_continuation(self):
        self.w.running=True;[self.w.step() for _ in range(30)];other=World.load(self.w.save());other.running=True
        for _ in range(100): self.w.step();other.step()
        self.assertEqual(self.w.members,other.members);self.assertEqual(self.w.events,other.events)
    def test_invalid_save(self):
        with self.assertRaises(ValueError): World.load({'version':7})
    def test_invalid_members(self):
        s=self.w.save();s['state']['members']=[]
        with self.assertRaises(ValueError): World.load(s)
    def test_invalid_nan(self):
        s=self.w.save();s['state']['stats']['budget']=float('nan')
        with self.assertRaises(ValueError): World.load(s)
    def test_invalid_profile(self): self.assertIsNone(validate_profile({'axes':[999]*7},self.w.parties))
    def test_valid_profile(self):
        p={k:v for k,v in self.w.law_profile.items() if k!='source'}; self.assertIsNotNone(validate_profile(p,self.w.parties))
    def test_invalid_proposal(self): self.assertFalse(self.w.apply_proposal({'actor':1,'action':'delete','text':'oops'}))
    def test_valid_proposal(self):
        self.w.running=True;self.a['cooldown']=0;self.assertTrue(self.w.apply_proposal({'actor':1,'target':26,'action':'chat','text':'Wir reden.'}))
    def test_stale_proposal(self): self.assertFalse(self.w.apply_proposal({'actor':1,'action':'speech','text':'Hi'}))
    def test_long_simulation(self):
        for seed in (7,42,75):
            w=World(seed);w.running=True;w.chaos=3
            for _ in range(1500):w.step()
            self.assertEqual(len(w.members),63);self.assertLessEqual(len(w.events),600)
            self.assertTrue(all(0<=v<=100 for v in w.stats.values()))
            self.assertTrue(all(0<=m['loyalty']<=100 for m in w.members))
            World.load(w.save())

class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g=Game();cls.s=Server(('127.0.0.1',0),cls.g);cls.t=threading.Thread(target=cls.s.serve_forever,daemon=True);cls.t.start();cls.url=f'http://127.0.0.1:{cls.s.server_port}'
    @classmethod
    def tearDownClass(cls): cls.s.shutdown();cls.s.server_close()
    def post(self,p,token=True,origin=None):
        headers={'Content-Type':'application/json'}
        if token:headers['X-Game-Token']=self.g.token
        if origin:headers['Origin']=origin
        return urllib.request.urlopen(urllib.request.Request(self.url+'/api/control',data=json.dumps(p).encode(),headers=headers))
    def test_state(self): self.assertEqual(len(json.load(urllib.request.urlopen(self.url+'/api/state'))['members']),63)
    def test_no_token(self):
        with self.assertRaises(urllib.error.HTTPError) as e:self.post({'action':'run'},False)
        self.assertEqual(e.exception.code,403)
    def test_wrong_origin(self):
        with self.assertRaises(urllib.error.HTTPError) as e:self.post({'action':'run'},origin='https://evil.invalid')
        self.assertEqual(e.exception.code,403)
    def test_control(self): self.assertTrue(json.load(self.post({'action':'run'}))['running'])
    def test_bad_settings(self):
        with self.assertRaises(urllib.error.HTTPError) as e:self.post({'action':'settings','speed':999})
        self.assertEqual(e.exception.code,400)
    def test_sandbox_gate(self):
        with self.assertRaises(urllib.error.HTTPError):self.post({'action':'intervene','kind':'election'})
    def test_unknown_action(self):
        with self.assertRaises(urllib.error.HTTPError):self.post({'action':'destroy'})
    def test_html(self): self.assertIn(b'AFFENK',urllib.request.urlopen(self.url).read())
    def test_path_traversal(self):
        with self.assertRaises(urllib.error.HTTPError): urllib.request.urlopen(self.url+'/../engine.py')
    def test_download(self): self.assertEqual(json.load(urllib.request.urlopen(self.url+'/api/save'))['version'],7)

if __name__=='__main__':unittest.main()
