"""Seeded autonomous agents. LLM output never directly mutates the world."""
import copy
import math
import random
import re
from config import PARTIES,FIRST,LAST,PERSONALITIES,DEFAULT_LAW,WORLD_DEFAULTS,ACTIONS

def clamp(x,lo=0,hi=100): return max(lo,min(hi,x))
def affinity(a,b): return 1-sum(abs(x-y) for x,y in zip(a,b))/(200*len(a))

class World:
    def __init__(self,seed=42,chaos=1.45):
        self.seed=seed; self.rng=random.Random(seed); self.chaos=float(clamp(chaos,.1,3))
        self.tick=0; self.running=False; self.phase='debatte'; self.phase_until=0
        self.session=1; self.election=0; self.parties=copy.deepcopy(PARTIES); self.stats=WORLD_DEFAULTS.copy()
        self.members=[]; self.events=[]; self.event_seq=0; self.effects=[]; self.laws=[]
        self.law=DEFAULT_LAW; self.law_profile=self.analyse_law(self.law); self.debate_count=0
        self.votes=None; self.amendment=None; self.amendment_votes=None; self.speaker=None; self.speech_until=0
        self.coalition=['CDU','CSU','SPD']; self.coalition_cohesion=75.
        self.last_election=-120; self.last_brawl=-30; self.last_streaker=-100; self.last_crisis=-100
        self.absurdity=75; self.ai_enabled=False; self.ai_status='Aus: läuft auch ohne Modell'
        used=set(); n=1
        for party,cfg in self.parties.items():
            for _ in range(cfg['seats']):
                name=self.rng.choice(FIRST)+' '+self.rng.choice(LAST)
                while name in used: name=self.rng.choice(FIRST)+' '+self.rng.choice(LAST)
                used.add(name)
                # Three rows, 21 seats: all 63 agents exist and are drawn.
                row=(n-1)//21; col=(n-1)%21; angle=math.pi+math.pi*col/20
                radius=.25+row*.10
                home=[.5+math.cos(angle)*radius,.59+math.sin(angle)*radius]
                m={'id':n,'name':name,'party':party,'personality':self.rng.choice(PERSONALITIES),
                   'values':[clamp(v+self.rng.randint(-35,35),-100,100) for v in cfg['values']],
                   'stress':float(self.rng.randint(5,30)),'ambition':float(self.rng.randint(20,95)),
                   'loyalty':float(self.rng.randint(35,90)),'energy':float(self.rng.randint(60,100)),
                   'influence':float(self.rng.randint(20,65)),'anger':0.,'scandal':0.,'persuasion':0.,
                   'state':'seated','goal':self.rng.choice(['Einfluss','Überzeugung','Zusammenhalt','Aufmerksamkeit']),
                   'position':home[:],'destination':home[:],'home':home,'relations':{},'memory':[],
                   'cooldown':self.rng.randint(1,8),'until':0,'vote':None,'reason':'','bubble':'','bubble_until':0,
                   'speeches':0,'deals':0,'sanctions':0,'resigned':False,'ban_until':0}
                self.members.append(m); n+=1
        for m in self.members:
            for other in self.rng.sample([o for o in self.members if o is not m],4): m['relations'][str(other['id'])]=self.rng.randint(-30,30)
        self.log('opening','Sitzung eröffnet: 63 fiktive Parodiefiguren; Sitzverteilung der Wahl 2025.',[])
    def get(self,mid): return next((m for m in self.members if m['id']==mid),None)
    def active(self): return [m for m in self.members if not m['resigned'] and m['ban_until']<=self.tick and m['state'] not in ('outside','evacuated')]
    def seats(self): return {p:sum(m['party']==p and not m['resigned'] for m in self.members) for p in self.parties}
    def rel(self,a,b): return a['relations'].get(str(b['id']),0)
    def change_rel(self,a,b,d): a['relations'][str(b['id'])]=clamp(self.rel(a,b)+d,-100,100)
    def log(self,kind,text,actors,cause='',duration=10,data=None):
        self.event_seq+=1
        e={'id':self.event_seq,'tick':self.tick,'kind':kind,'text':text,'actors':actors,'cause':cause,'data':data or {}}
        self.events.append(e); self.events=self.events[-600:]
        if duration: self.effects.append({**e,'until':self.tick+duration})
        for mid in actors:
            m=self.get(mid)
            if m: m['memory'].append({k:e[k] for k in ('tick','kind','text','cause')}); m['memory']=m['memory'][-16:]
        return e
    def say(self,m,text): m['bubble']=text[:180]; m['bubble_until']=self.tick+10
    def move(self,m,state,dest,duration): m['state']=state; m['destination']=list(dest); m['until']=self.tick+duration if duration else 0
    def analyse_law(self,text):
        t=text.lower(); axes=[0]*7
        pats=[(0,r'reform|modern|digital|gleichstell',40),(1,r'klima|energie|emission|umwelt|erneuerbar',45),
          (1,r'kohle|fossil|ölbohr',-45),(2,r'sozial|rente|kindergeld|miete|pflege|gesundheit|förder',40),
          (2,r'kürz|leistung.*streich',-45),(3,r'pflicht|verbot|staatlich|öffentlich|regulier',-45),
          (3,r'privatis|deregulier|freiwillig',45),(4,r'\beu\b|europa|international|grenzüberschreit',40),
          (4,r'grenzkontrolle|national|abschieb',-45),(5,r'freiheit|datenschutz|selbstbestimm',45),
          (5,r'überwach|daten.*pflicht|abschaff|verbiet',-45),(6,r'wirtschaft|invest|industrie|arbeitsplatz|steuersenk',40),
          (6,r'steuererhöh|zusatzkosten|belastung',-40)]
        for i,pat,v in pats:
            if re.search(pat,t): axes[i]=clamp(axes[i]+v,-100,100)
        effects={k:0. for k in WORLD_DEFAULTS}
        effects.update(ecology=axes[1]*.12,welfare=axes[2]*.1,economy=axes[6]*.1,freedom=axes[5]*.1,
                       budget=-(max(0,axes[2])+max(0,axes[6]))*.055,trust=1.5)
        target=next((p for p in self.parties if re.search(r'(?<!\w)'+re.escape(p.lower())+r'(?!\w)',t)),None)
        op={'kind':'dissolve_party','party':target} if target and re.search(r'abschaff|abgeschaff|verbiet|verbot|auflös|aufgelös',t) else None
        return {'axes':axes,'effects':effects,'operation':op,'source':'heuristische Spielauslegung, keine reale Prognose'}
    def set_law(self,text):
        text=' '.join(str(text).split())
        if not 5<=len(text)<=1200: raise ValueError('Gesetz muss 5 bis 1200 Zeichen haben.')
        if self.phase in ('abstimmung','aenderung','evakuierung','wahl'): raise ValueError('Entwurf in dieser Phase nicht wechseln.')
        self.law=text; self.law_profile=self.analyse_law(text); self.debate_count=0; self.votes=None; self.amendment=None; self.amendment_votes=None
        for m in self.members: m['persuasion']=0.; m['vote']=None
        self.log('law','Neuer Entwurf: '+text,[],data=self.law_profile)
    def policy(self,m,profile=None):
        pairs=[a*v/10000 for a,v in zip((profile or self.law_profile)['axes'],m['values']) if a]
        return sum(pairs)/len(pairs) if pairs else 0.
    def select_target(self,m):
        others=[o for o in self.active() if o is not m]
        return self.rng.choices(others,weights=[1+abs(self.rel(m,o))/15+(1-affinity(m['values'],o['values']))*2 for o in others])[0] if others else None
    def choose_action(self,m,target):
        hostile=max(0,-self.rel(m,target))/100 if target else 0; friendly=max(0,self.rel(m,target))/100 if target else 0
        tension=(m['stress']+m['anger'])/200
        w={'chat':2+friendly*3,'speech':.7+m['ambition']/100,'heckle':.1+tension*1.5+hostile,
           'deal':.15+m['ambition']/170+friendly,'protest':tension*.7,
           'brawl':max(0,tension-.3)*(hostile+.08)*self.chaos*(.4+self.absurdity/100),
           'walkout':max(0,m['stress']-48)/90,'resign':max(0,m['stress']-78)/110+max(0,m['scandal']-65)/180,
           'switch':max(0,35-m['loyalty'])/90,'split':max(0,m['ambition']-70)/200*max(0,40-m['loyalty'])/40}
        if m['personality'] in ('konfrontativ','spontan','leidenschaftlich'): w['heckle']*=1.8; w['brawl']*=2
        if self.phase!='debatte' or self.speaker is not None: w['speech']=0
        if len(self.parties)>=12: w['split']=0
        if m['energy']<25: w['walkout']+=2
        if not target:
            for a in ('chat','heckle','deal','brawl'): w[a]=0
        keys=[k for k in w if w[k]>0]
        return self.rng.choices(keys,weights=[w[k] for k in keys])[0]
    def act(self,m,action,target=None,forced=False):
        if action not in ACTIONS or not m or m['resigned']: return False
        if action!='return' and (m['ban_until']>self.tick or self.phase in ('evakuierung','wahl')): return False
        if target and (target is m or target['resigned']): return False
        if action in ('chat','deal') and target and target['state']!='seated': return False
        if action in ('chat','deal','heckle','brawl') and not target: return False
        cause=f"{m['personality']}; Stress {m['stress']:.0f}, Ehrgeiz {m['ambition']:.0f}, Treue {m['loyalty']:.0f}"
        if target: cause+=f", Beziehung {self.rel(m,target):+.0f}"
        if forced: cause='Sandbox-Eingriff; '+cause
        m['cooldown']=self.tick+self.rng.randint(5,13); m['energy']=clamp(m['energy']-self.rng.uniform(1,4))
        if action=='speech':
            if self.speaker is not None or self.phase!='debatte': return False
            self.speaker=m['id']; self.speech_until=self.tick+12; self.move(m,'speaking',[.5,.70],12)
            m['speeches']+=1; self.debate_count+=1; m['influence']=clamp(m['influence']+2)
            score=self.policy(m)
            text='Dafür, aber mit klaren Regeln!' if score>.1 else ('Das geht zu weit!' if score<-.1 else 'Wer bezahlt das eigentlich?')
            self.say(m,text)
            for o in self.active():
                if o is m: continue
                fit=affinity(o['values'],m['values']); self.change_rel(o,m,(fit-.5)*3)
                o['persuasion']=clamp(o['persuasion']+score*(fit-.3)*.03,-.3,.3)
                if fit<.4: o['stress']=clamp(o['stress']+self.chaos*2)
            self.log('speech',f"{m['name']} spricht: {text}",[m['id']],cause,12)
        elif action=='chat':
            self.move(m,'chatting',[target['position'][0]+.025,target['position'][1]+.025],7)
            delta=(affinity(m['values'],target['values'])-.45)*10
            self.change_rel(m,target,delta); self.change_rel(target,m,delta*.7)
            m['stress']=clamp(m['stress']-4); target['stress']=clamp(target['stress']-2); self.say(m,'Unter vier Augen?')
            self.log('chat',f"{m['name']} sucht das Gespräch mit {target['name']}.",[m['id'],target['id']],cause,7)
        elif action=='heckle':
            self.say(m,self.rng.choice(['Unfug!','Zur Sache!','Das ist doch Theater!','Wer hat das gerechnet?','Nicht mit uns!']))
            self.change_rel(m,target,-6); self.change_rel(target,m,-9)
            target['stress']=clamp(target['stress']+8*self.chaos); target['anger']=clamp(target['anger']+7*self.chaos)
            m['stress']=clamp(m['stress']+2); m['influence']=clamp(m['influence']+1)
            if m['party'] in self.coalition and target['party'] in self.coalition and m['party']!=target['party']: self.coalition_cohesion=clamp(self.coalition_cohesion-4)
            self.log('heckle',f"{m['name']} unterbricht {target['name']}.",[m['id'],target['id']],cause,8)
        elif action=='deal':
            self.move(m,'dealing',[.80,.74],9); self.move(target,'dealing',[.85,.74],9)
            succeeds=self.rng.random()<clamp(.25+self.rel(m,target)/200+affinity(m['values'],target['values'])*.4,.05,.9)
            if succeeds:
                self.change_rel(m,target,12); self.change_rel(target,m,12)
                target['persuasion']=clamp(target['persuasion']+self.policy(m)*.18,-.3,.3)
                m['deals']+=1; m['influence']=clamp(m['influence']+4); m['loyalty']=clamp(m['loyalty']-3)
                text='Ein Hinterzimmer-Deal kommt zustande.'
            else:
                self.change_rel(m,target,-6); m['stress']=clamp(m['stress']+5); text='Der Deal platzt.'
            self.say(m,'Ein kleiner Kompromiss ...')
            self.log('deal',f"{m['name']} / {target['name']}: {text}",[m['id'],target['id']],cause,9)
            if succeeds and self.rng.random()<.13*self.chaos:
                m['scandal']=clamp(m['scandal']+25); self.stats['trust']=clamp(self.stats['trust']-4)
                self.log('scandal',f"Die Absprache von {m['name']} wird öffentlich.",[m['id']],'Geheimer Deal entdeckt',12)
        elif action=='protest':
            self.move(m,'protesting',[.3+self.rng.random()*.4,.60],10); self.say(m,'SO NICHT!')
            allies=[o for o in self.active() if o is not m and (self.rel(o,m)>20 or o['party']==m['party'])]
            allies=self.rng.sample(allies,min(len(allies),self.rng.randint(1,4)))
            for i,o in enumerate(allies): self.move(o,'protesting',[.35+i*.06,.62],10); o['anger']=clamp(o['anger']+5)
            self.stats['stability']=clamp(self.stats['stability']-1)
            self.log('protest',f"{m['name']} beginnt eine Sitzblockade; {len(allies)} schließen sich an.",[m['id']]+[o['id'] for o in allies],cause,10)
        elif action=='brawl':
            if not forced and self.tick-self.last_brawl<20: return False
            self.last_brawl=self.tick
            if self.speaker in (m['id'],target['id']): self.speaker=None
            center=[(m['position'][0]+target['position'][0])/2,(m['position'][1]+target['position'][1])/2]
            self.move(m,'fighting',center,6); self.move(target,'fighting',[center[0]+.035,center[1]],6)
            self.change_rel(m,target,-25); self.change_rel(target,m,-25)
            m['scandal']=clamp(m['scandal']+18); target['scandal']=clamp(target['scandal']+12)
            m['stress']=clamp(m['stress']+8); target['stress']=clamp(target['stress']+12)
            m['sanctions']+=1; target['sanctions']+=1; m['ban_until']=self.tick+20; target['ban_until']=self.tick+16
            self.stats['trust']=clamp(self.stats['trust']-4); self.stats['stability']=clamp(self.stats['stability']-6)
            self.log('brawl',f"{m['name']} und {target['name']} geraten aneinander. Sicherheitsdienst greift ein.",[m['id'],target['id']],cause,10)
            if m['party'] in self.coalition and target['party'] in self.coalition and m['party']!=target['party']: self.coalition_cohesion=clamp(self.coalition_cohesion-12)
        elif action=='walkout':
            self.move(m,'outside',[1.05,.82],self.rng.randint(16,30)); m['anger']=clamp(m['anger']-8)
            self.log('walkout',f"{m['name']} verlässt demonstrativ den Saal.",[m['id']],cause,10)
        elif action=='return':
            if m['ban_until']>self.tick: return False
            self.move(m,'seated',m['home'],0); self.log('return',f"{m['name']} kehrt zurück.",[m['id']],'Pause beendet',6)
        elif action=='resign':
            m['resigned']=True
            if self.speaker==m['id']: self.speaker=None
            self.move(m,'resigned',[1.05,.88],0); self.stats['trust']=clamp(self.stats['trust']-2)
            self.log('resign',f"{m['name']} legt das Mandat nieder. Sitz bleibt bis zur Wahl leer.",[m['id']],cause,15); self.check_majority()
        elif action=='switch':
            others=[p for p in self.parties if p!=m['party'] and p!='Fraktionslos']
            if not others: return False
            best=max(others,key=lambda p:affinity(m['values'],self.parties[p]['values']))
            old=m['party']; m['party']=best; m['loyalty']=50
            self.log('switch',f"{m['name']} wechselt von {old} zu {best}.",[m['id']],cause,12); self.check_majority()
        elif action=='split':
            if len(self.parties)>=12: return False
            old=m['party']; new='Freie Liste '+m['name'].split()[-1]
            if new in self.parties: return False
            self.parties[new]={'short':'FL'+str(len(self.parties)),'color':self.rng.choice(['#ffc36e','#69dedb','#f18fd2','#a9c768']),'seats':0,'values':m['values'][:]}
            followers=[o for o in self.active() if o is not m and o['party']==old and (self.rel(o,m)>8 or o['loyalty']<35)]
            followers=self.rng.sample(followers,min(len(followers),5))
            for o in [m]+followers: o['party']=new; o['loyalty']=60
            self.log('split',f"{m['name']} gründet {new}; {len(followers)} folgen.",[m['id']]+[o['id'] for o in followers],cause,16); self.check_majority()
        return True
    def check_majority(self):
        seats=self.seats()
        if self.coalition and sum(seats.get(p,0) for p in self.coalition)<=sum(seats.values())/2: self.break_coalition('Sitzmehrheit verloren')
    def break_coalition(self,cause='Konflikte überwiegen'):
        if not self.coalition: return False
        self.coalition=[]; self.coalition_cohesion=0; self.stats['stability']=clamp(self.stats['stability']-12)
        self.log('coalition_break','Die Koalition zerbricht. Minderheitsbetrieb bis zur nächsten Wahl.',[],cause,18); return True
    def evacuate(self,cause='Unruhe eskaliert'):
        self.phase='evakuierung'; self.phase_until=self.tick+16; self.speaker=None
        for m in self.members:
            if not m['resigned']: self.move(m,'evacuated',[1.06,.82+(m['id']%4)*.03],16)
        self.stats['stability']=clamp(self.stats['stability']-5)
        self.log('evacuate','Präsidium lässt den Saal räumen. Sitzung unterbrochen.',[],cause,16)
    def streaker(self,forced=False):
        if self.phase=='evakuierung': return False
        if not forced and self.tick-self.last_streaker<80: return False
        self.last_streaker=self.tick
        self.log('streaker','Flitzer im hautfarbenen Ganzkörperkostüm! Sicherheitsdienst folgt.',[],'Cartoon-Satire ohne Nacktdarstellung',12)
        for m in self.active(): m['anger']=clamp(m['anger']+3); m['stress']=clamp(m['stress']+3)
        return True
    def absurd_event(self):
        kind=self.rng.choice(['confetti','goose','blackout','coffee'])
        descriptions={'confetti':'Die Konfettikanone des Präsidiums explodiert bei einem Zwischenruf.',
          'goose':'Eine Gans besetzt das Rednerpult. Niemand will zuständig sein.',
          'blackout':'Lichtausfall. Die Debatte geht mit Handylichtern weiter.',
          'coffee':'Kaffeekrise: Der Automat ist leer. Die Stimmung kippt.'}
        self.log(kind,descriptions[kind],[],f'Absurdität {self.absurdity}/100; zufälliger äußerer Auslöser',12)
        for m in self.active(): m['stress']=clamp(m['stress']+(8 if kind=='coffee' else 2))
    def call_election(self,cause='Regierungskrise'):
        if self.phase=='wahl': return False
        self.phase='wahl'; self.phase_until=self.tick+12; self.speaker=None
        self.log('election','Neuwahl ausgerufen. Mandate und Mehrheiten werden neu verteilt.',[],cause,12); return True
    def finish_election(self):
        self.election+=1; self.last_election=self.tick
        parties=[p for p in self.parties if p!='Fraktionslos']; seats=self.seats()
        weights={p:max(1.,seats.get(p,0)*(1.2 if p not in self.coalition else .9)+self.rng.uniform(1,5)) for p in parties}
        for m in self.members:
            m['resigned']=False; m['ban_until']=0
            fit=[weights[p]*(.2+affinity(m['values'],self.parties[p]['values'])) for p in parties]
            m['party']=self.rng.choices(parties,weights=fit)[0]
            m['stress']=self.rng.uniform(5,25); m['anger']=0.; m['energy']=85.; m['scandal']*=.4; m['loyalty']=self.rng.uniform(40,80)
            self.move(m,'seated',m['home'],0)
        # Game coalition search penalizes ideologically distant partners.
        counts=self.seats(); leader=max(parties,key=lambda p:counts[p]); self.coalition=[leader]
        remaining=sorted([p for p in parties if p!=leader],key=lambda p:counts[p]*affinity(self.parties[leader]['values'],self.parties[p]['values']),reverse=True)
        for p in remaining:
            if sum(counts[q] for q in self.coalition)>len(self.members)/2: break
            self.coalition.append(p)
        self.coalition_cohesion=75.; self.stats['stability']=clamp(self.stats['stability']+25); self.stats['trust']=clamp(self.stats['trust']+8)
        self.phase='debatte'; self.debate_count=0; self.votes=None
        self.log('election_result','Wahl beendet. Neue Spielkoalition: '+', '.join(self.coalition),[],'Fiktive Neuverteilung, keine Wahlprognose',15,data={'seats':self.seats()})
    def begin_amendment(self):
        pool=self.active()
        if not pool: self.evacuate('Keine Figuren im Saal'); return
        author=self.rng.choice(pool); profile=copy.deepcopy(self.law_profile)
        profile['effects']={k:v*.65 for k,v in profile['effects'].items()}; profile['axes']=[round(x*.65) for x in profile['axes']]
        self.amendment={'author':author['id'],'text':'Umsetzungsumfang auf 65 % begrenzen; Wirkung und Budget neu berechnen.','profile':profile}
        self.phase='aenderung'; self.phase_until=self.tick+8; self.say(author,'Ein Kompromiss: kleiner anfangen!')
        self.log('amendment',f"{author['name']} schlägt geringeren Umsetzungsumfang vor.",[author['id']],'Interessenausgleich',8)
    def vote(self,profile=None,amendment=False):
        profile=profile or self.law_profile; counts={'ja':0,'nein':0,'enthalten':0,'abwesend':0}; reasons=[]
        present={m['id'] for m in self.active()}
        for m in self.members:
            if m['resigned']: continue
            if m['id'] not in present: choice='abwesend'; score=0; reason='Nicht im Saal / Saalverweis'
            else:
                policy=self.policy(m,profile); pv=self.parties[m['party']]['values']
                pairs=[a*v/10000 for a,v in zip(profile['axes'],pv) if a]; party=sum(pairs)/len(pairs) if pairs else 0
                score=policy*1.4+party*m['loyalty']/100*.3+m['persuasion']+self.rng.uniform(-.07,.07)
                choice='ja' if score>.16 else ('nein' if score<-.16 else 'enthalten')
                reason=f"Überzeugung {policy:+.2f}; Fraktion {party:+.2f}; Debatte {m['persuasion']:+.2f}"
                if not amendment:
                    agrees=(choice=='ja' and party>.1) or (choice=='nein' and party<-.1)
                    m['loyalty']=clamp(m['loyalty']+(2 if agrees else -2)); m['stress']=clamp(m['stress']-2)
            counts[choice]+=1
            if not amendment: m['vote']=choice; m['reason']=reason
            reasons.append({'id':m['id'],'vote':choice,'score':round(score,3),'reason':reason})
        quorum=counts['ja']+counts['nein']+counts['enthalten']>sum(not m['resigned'] for m in self.members)/2
        return {'counts':counts,'quorum':quorum,'passed':quorum and counts['ja']>counts['nein'],'reasons':reasons,'tick':self.tick}
    def resolve_amendment(self):
        self.amendment_votes=self.vote(self.amendment['profile'],True)
        if self.amendment_votes['passed']: self.law_profile=copy.deepcopy(self.amendment['profile'])
        self.log('amendment_result','Änderungsantrag '+('angenommen' if self.amendment_votes['passed'] else 'abgelehnt')+'.',[],'Mehrheit und Anwesenheit',7,data=self.amendment_votes)
        self.phase='abstimmung'; self.phase_until=self.tick+8
        self.log('vote_start','Endabstimmung: Jede Figur entscheidet selbst.',[],'Debatte abgeschlossen',8)
    def resolve_vote(self):
        self.votes=self.vote()
        if self.votes['passed']:
            for k,d in self.law_profile['effects'].items(): self.stats[k]=clamp(self.stats[k]+d)
            op=self.law_profile.get('operation')
            if op and op['kind']=='dissolve_party' and op['party'] in self.parties:
                old=op['party']; affected=[m for m in self.members if m['party']==old]; new='Fraktionslos'
                if new not in self.parties: self.parties[new]={'short':'LOS','color':'#c2b9a6','seats':0,'values':[0]*7}
                for m in affected: m['party']=new; m['loyalty']=0; m['anger']=clamp(m['anger']+45); m['stress']=clamp(m['stress']+35)
                del self.parties[old]; self.coalition=[p for p in self.coalition if p!=old]
                self.log('party_dissolved',f"Spielregel: {old} aufgelöst; {len(affected)} Figuren nun fraktionslos.",[m['id'] for m in affected],'Fiktiver Beschluss, keine reale Rechtsauskunft',18); self.check_majority()
            self.laws.append({'text':self.law,'tick':self.tick,'effects':copy.deepcopy(self.law_profile['effects']),'operation':copy.deepcopy(self.law_profile.get('operation'))})
        self.log('vote_result',('ANGENOMMEN' if self.votes['passed'] else ('NICHT BESCHLUSSFÄHIG' if not self.votes['quorum'] else 'ABGELEHNT'))+' · '+self.law,[],'Stimmen der anwesenden Figuren',18,data=self.votes)
        self.phase='ergebnis'; self.phase_until=self.tick+16
    def new_session(self):
        self.session+=1; self.phase='debatte'; self.debate_count=0; self.votes=None; self.amendment=None; self.amendment_votes=None
        topics=[('Öffentliche Schulen sollen energetisch saniert und digital ausgestattet werden.','ecology'),
          ('Für sozialen Wohnraum und Pflege soll ein Investitionsprogramm starten.','welfare'),
          ('Unternehmen sollen durch freiwillige Innovation und Steuersenkungen entlastet werden.','economy'),
          ('Ein Datenschutzgesetz soll mehr Freiheit und Selbstbestimmung sichern.','freedom')]
        law,_=min(topics,key=lambda x:self.stats[x[1]]+self.rng.uniform(-15,15))
        self.law=law; self.law_profile=self.analyse_law(law)
        for m in self.members: m['vote']=None; m['persuasion']*=.3
        self.log('session',f"Sitzung {self.session}: {law}",[],'Reaktion auf den Zustand der Spielwelt',12)
    def step(self):
        if not self.running: return
        self.tick+=1; self.effects=[e for e in self.effects if e['until']>self.tick]
        for m in self.members:
            for i in (0,1): m['position'][i]+=(m['destination'][i]-m['position'][i])*.25
            if m['bubble_until']<=self.tick: m['bubble']=''
            if m['resigned']: continue
            outside=m['state'] in ('outside','evacuated','ejected')
            m['energy']=clamp(m['energy']+(.8 if outside else .08))
            m['stress']=clamp(m['stress']+(-.7 if outside else -.10)+(.055*self.chaos if self.phase=='debatte' else 0))
            m['anger']=clamp(m['anger']-.22)
            if m['until'] and m['until']<=self.tick and self.phase!='evakuierung':
                if m['ban_until']>self.tick: self.move(m,'ejected',[1.07,.84],m['ban_until']-self.tick)
                else: self.move(m,'seated',m['home'],0)
        if self.phase=='evakuierung':
            if self.tick>=self.phase_until:
                for m in self.members:
                    if not m['resigned']: self.move(m,'seated',m['home'],0); m['stress']*=.6; m['anger']*=.4
                self.phase='debatte'; self.stats['stability']=clamp(self.stats['stability']+8)
                self.log('reopen','Saal wieder geöffnet. Figuren kehren zurück.',[],'Abkühlphase beendet',10)
            return
        if self.phase=='wahl':
            if self.tick>=self.phase_until: self.finish_election()
            return
        if self.speaker and self.tick>=self.speech_until:
            m=self.get(self.speaker)
            if m and not m['resigned'] and m['state']=='speaking': self.move(m,'seated',m['home'],0)
            self.speaker=None
        if self.phase in ('aenderung','abstimmung','ergebnis') and self.tick>=self.phase_until:
            if self.phase=='aenderung': self.resolve_amendment()
            elif self.phase=='abstimmung': self.resolve_vote()
            else: self.new_session()
        if self.phase=='debatte' and self.debate_count>=7 and self.speaker is None: self.begin_amendment()
        for _ in range(2):
            candidates=[m for m in self.active() if m['cooldown']<=self.tick and m['state']=='seated']
            if candidates:
                m=self.rng.choices(candidates,weights=[1+m['ambition']/50+m['stress']/40 for m in candidates])[0]
                target=self.select_target(m); self.act(m,self.choose_action(m,target),target)
        if self.phase=='debatte' and self.speaker is None and self.tick%5==0 and self.debate_count<7:
            pool=[m for m in self.active() if m['state']=='seated']
            if pool: self.act(self.rng.choice(pool),'speech')
        if self.tick%5==0:
            mean=sum(m['stress'] for m in self.members)/len(self.members)
            self.coalition_cohesion=clamp(self.coalition_cohesion+(.2 if mean<30 else -.4*self.chaos))
            if self.coalition and self.coalition_cohesion<22: self.break_coalition('Zusammenhalt unter 22 %')
            unrest=sum(m['state'] in ('protesting','fighting') for m in self.members)
            if unrest>=9 or (mean>65 and self.rng.random()<.15): self.evacuate(f'{unrest} Störer, Stressmittel {mean:.0f}')
            elif not self.coalition and self.tick-self.last_election>120 and self.stats['stability']<60: self.call_election()
        if self.absurdity and self.phase=='debatte' and self.rng.random()<.007*self.chaos*self.absurdity/100: self.streaker()
        if self.absurdity>=50 and self.phase=='debatte' and self.rng.random()<.005*self.absurdity/100: self.absurd_event()
        if self.tick-self.last_crisis>70 and self.rng.random()<.008*self.chaos:
            self.last_crisis=self.tick; crisis=self.rng.choice(['budget','economy','ecology']); self.stats[crisis]=clamp(self.stats[crisis]-8)
            for m in self.active(): m['stress']=clamp(m['stress']+6*self.chaos); m['loyalty']=clamp(m['loyalty']-1)
            self.log('crisis','Weltkrise: '+{'budget':'Haushaltsloch','economy':'Wirtschaftsflaute','ecology':'Umweltschaden'}[crisis],[],'Äußerer Druck verstärkt bestehende Konflikte',14,data={'stat':crisis,'delta':-8})
        if self.coalition and self.tick%12==0:
            gov=[m for m in self.active() if m['party'] in self.coalition]
            if gov:
                hostility=sum(max(0,-self.rel(m,o)) for m in gov for o in gov if m['party']!=o['party'])/max(1,len(gov)**2)
                self.coalition_cohesion=clamp(self.coalition_cohesion-hostility*.12*self.chaos)
    def intervene(self,kind,mid=None,target=None):
        if kind in ACTIONS: return self.act(self.get(mid),kind,self.get(target),True)
        if kind=='evacuate': self.evacuate('Sandbox-Eingriff'); return True
        if kind=='coalition_break': return self.break_coalition('Sandbox-Eingriff')
        if kind=='election': return self.call_election('Sandbox-Eingriff')
        if kind=='streaker': return self.streaker(True)
        if kind=='heat':
            for m in self.active(): m['stress']=clamp(m['stress']+25); m['anger']=clamp(m['anger']+20); m['loyalty']=clamp(m['loyalty']-8)
            self.log('heat','Stimmung kippt. Bestehende Konflikte werden verschärft.',[],'Sandbox-Eingriff',12); return True
        raise ValueError('Unbekannter Eingriff')
    def apply_proposal(self,p):
        if not isinstance(p,dict): return False
        mid=p.get('actor'); target=p.get('target'); action=p.get('action'); text=p.get('text','')
        if type(mid) is not int or (target is not None and type(target) is not int): return False
        if action not in ('chat','heckle','deal','protest','walkout','speech') or not isinstance(text,str) or len(text)>500: return False
        m=self.get(mid); t=self.get(target)
        if not m or m['state']!='seated' or m['cooldown']>self.tick or not self.running: return False
        if self.act(m,action,t):
            if text: self.say(m,text)
            return True
        return False
    def snapshot(self):
        keys=('seed','tick','running','phase','session','election','chaos','absurdity','stats','parties','members','law','law_profile','debate_count','speaker','votes','amendment','amendment_votes','coalition','coalition_cohesion','effects','ai_enabled','ai_status')
        out={k:copy.deepcopy(getattr(self,k)) for k in keys}; out['seats']=self.seats(); out['events']=copy.deepcopy(self.events[-120:]); out['laws']=copy.deepcopy(self.laws[-40:])
        return out
    def save(self):
        attrs={k:copy.deepcopy(v) for k,v in self.__dict__.items() if k!='rng'}; attrs['running']=False
        return {'format':'AFFENKAEFIG','version':7,'state':attrs,'random_state':self.rng.getstate()}
    @classmethod
    def load(cls,data):
        import json
        if not isinstance(data,dict) or data.get('format')!='AFFENKAEFIG' or data.get('version')!=7: raise ValueError('Kein gültiger v7-Spielstand')
        s=data.get('state'); baseline=cls()
        if not isinstance(s,dict) or set(s)!=set(k for k in baseline.__dict__ if k!='rng'): raise ValueError('Weltzustand unvollständig')
        if len(json.dumps(s,allow_nan=False))>2000000: raise ValueError('Welt zu groß')
        def num(x,lo=-1000000,hi=1000000): return type(x) in (int,float) and math.isfinite(x) and lo<=x<=hi
        if type(s['tick']) is not int or s['tick']<0 or not isinstance(s['members'],list) or len(s['members'])!=63: raise ValueError('Ungültige Welt')
        if not isinstance(s['parties'],dict) or not 1<=len(s['parties'])<=13: raise ValueError('Ungültige Parteien')
        if len(s['events'])>600 or len(s['effects'])>600 or len(s['laws'])>10000: raise ValueError('Welt zu groß')
        if s['phase'] not in ('debatte','aenderung','abstimmung','ergebnis','evakuierung','wahl'): raise ValueError('Ungültige Phase')
        for key in WORLD_DEFAULTS:
            if not num(s['stats'].get(key),0,100): raise ValueError('Ungültige Weltwerte')
        for p,cfg in s['parties'].items():
            if not isinstance(p,str) or len(p)>100 or not isinstance(cfg,dict): raise ValueError('Ungültige Partei')
            if not isinstance(cfg.get('values'),list) or len(cfg['values'])!=7 or any(not num(v,-100,100) for v in cfg['values']): raise ValueError('Ungültige Parteiwerte')
            if not re.fullmatch(r'#[0-9a-fA-F]{6}',str(cfg.get('color',''))): raise ValueError('Ungültige Farbe')
            if not isinstance(cfg.get('short'),str) or len(cfg['short'])>15: raise ValueError('Ungültiges Kürzel')
        ids=set(); expected=set(baseline.members[0])
        for m in s['members']:
            if not isinstance(m,dict) or set(m)!=expected or type(m['id']) is not int or m['id'] in ids: raise ValueError('Ungültige Figuren')
            ids.add(m['id'])
            if m['party'] not in s['parties'] or m['state'] not in ('seated','chatting','dealing','speaking','protesting','fighting','outside','evacuated','ejected','resigned'): raise ValueError('Ungültige Figur')
            for k in ('name','personality','goal','reason','bubble'):
                if not isinstance(m[k],str) or len(m[k])>1000: raise ValueError('Ungültiger Text')
            for k in ('stress','ambition','loyalty','energy','influence','anger','scandal'):
                if not num(m[k],0,100): raise ValueError('Ungültige Figurenwerte')
            for k in ('position','destination','home'):
                if not isinstance(m[k],list) or len(m[k])!=2 or any(not num(v,-2,2) for v in m[k]): raise ValueError('Ungültige Position')
            if not isinstance(m['values'],list) or len(m['values'])!=7 or any(not num(v,-100,100) for v in m['values']): raise ValueError('Ungültige Politikwerte')
            if not isinstance(m['relations'],dict) or len(m['relations'])>63 or any(not num(v,-100,100) for v in m['relations'].values()): raise ValueError('Ungültige Beziehungen')
            if not isinstance(m['memory'],list) or len(m['memory'])>16: raise ValueError('Ungültige Erinnerung')
            for k in ('cooldown','until','bubble_until','speeches','deals','sanctions','ban_until'):
                if not num(m[k],0): raise ValueError('Ungültiger Timer')
            if not num(m['persuasion'],-.3,.3) or type(m['resigned']) is not bool: raise ValueError('Ungültige Figur')
        if ids!=set(range(1,64)): raise ValueError('Ungültige IDs')
        if not isinstance(s['coalition'],list) or any(p not in s['parties'] for p in s['coalition']): raise ValueError('Ungültige Koalition')
        if not num(s['chaos'],.1,3) or not num(s['coalition_cohesion'],0,100) or not num(s['absurdity'],0,100): raise ValueError('Ungültige Einstellung')
        def tup(v): return tuple(tup(x) for x in v) if isinstance(v,(list,tuple)) else v
        try: baseline.rng.setstate(tup(data['random_state']))
        except (ValueError,TypeError,KeyError): raise ValueError('Ungültiger Zufallszustand')
        baseline.__dict__.update(copy.deepcopy(s)); baseline.running=False; baseline.ai_status='Spielstand geladen; pausiert'
        # Prove the deserialized state supports its next transition before accepting.
        probe=copy.deepcopy(baseline); probe.running=True
        try: probe.step(); probe.snapshot()
        except Exception as exc: raise ValueError('Inkonsistenter Weltzustand') from exc
        return baseline
