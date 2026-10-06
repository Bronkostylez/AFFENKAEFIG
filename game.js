'use strict';
const $=id=>document.getElementById(id), esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let world=null,selected=1,partyFilter=null,token='',busy=false,lastSeq=0,lastTick=-1, toastTimer,positions=new Map(),mouse=null;
const canvas=$('scene'),ctx=canvas.getContext('2d');
const stateLabels={seated:'am Platz',speaking:'am Rednerpult',chatting:'im Gespräch',dealing:'im Hinterzimmer',protesting:'in der Sitzblockade',fighting:'im Streit',outside:'außerhalb',ejected:'Saalverweis',evacuated:'Saal geräumt',resigned:'zurückgetreten'};
const kindLabels={opening:'Sitzung',speech:'Rede',chat:'Gespräch',heckle:'Zwischenruf',deal:'Deal',protest:'Blockade',brawl:'Prügelei',walkout:'Saal verlassen',resign:'Rücktritt',switch:'Wechsel',split:'Abspaltung',coalition_break:'Koalitionsbruch',evacuate:'Saalräumung',reopen:'Wiedereröffnung',election:'Neuwahl',election_result:'Wahlergebnis',streaker:'Flitzer',scandal:'Skandal',vote_start:'Abstimmung',vote_result:'Ergebnis',amendment:'Änderungsantrag',amendment_result:'Änderung',law:'Entwurf',session:'Sitzung',crisis:'Weltkrise',heat:'Eskalation',confetti:'Konfetti',goose:'Gans',blackout:'Lichtausfall',coffee:'Kaffeekrise',interpretation:'Auslegung',party_dissolved:'Auflösung'};
const conflictKinds=['brawl','protest','evacuate','coalition_break','resign','split','switch','streaker','scandal','election','crisis','party_dissolved'];
const statNames={economy:'Wirtschaft',ecology:'Ökologie',welfare:'Soziales',freedom:'Freiheit',trust:'Vertrauen',stability:'Stabilität',budget:'Haushalt'};
function toast(msg,error=false){$('toast').textContent=msg;$('toast').className=error?'error':'';$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,4500)}
async function control(data){if(!token)return toast('Noch keine Verbindung.',true);try{const r=await fetch('/api/control',{method:'POST',headers:{'Content-Type':'application/json','X-Game-Token':token},body:JSON.stringify(data)});const j=await r.json();if(!r.ok)throw Error(j.error||'Aktion fehlgeschlagen');world=j;render();return true}catch(e){toast(e.message,true);return false}}
async function poll(){if(busy)return;busy=true;try{const r=await fetch('/api/state');if(!r.ok)throw Error('Server nicht erreichbar');world=await r.json();$('connection').textContent=world.running?'● LIVE / VERBUNDEN':'● PAUSIERT / VERBUNDEN';render()}catch(e){$('connection').textContent='● VERBINDUNG UNTERBROCHEN';$('connection').style.color='#ff677d'}finally{busy=false}}
function render(){if(!world)return;
 $('run').textContent=world.running?'Ⅱ Pause':'▶ Sitzung starten';$('session').textContent='SITZUNG '+String(world.session).padStart(2,'0')+' / WAHL '+world.election;
 $('clock').textContent='T+'+String(world.tick).padStart(4,'0');$('round').textContent='REDE '+world.debate_count+' / 7';
 const phases={debatte:'Das Plenum lebt.',aenderung:'Ein Kompromiss steht im Raum.',abstimmung:'Jetzt zählt jede Stimme.',ergebnis:world.votes?.passed?'Beschlossen. Mit Folgen.':'Keine Mehrheit.',evakuierung:'Sitzung unterbrochen.',wahl:'Die Macht wird neu verteilt.'};$('phase').textContent=phases[world.phase]||world.phase;
 if(document.activeElement!==$('law'))$('law').value=world.law;
 $('lawform').querySelector('button').disabled=['aenderung','abstimmung','evakuierung','wahl'].includes(world.phase);
 const effects=Object.entries(world.law_profile.effects).filter(([k,v])=>Math.abs(v)>.01).map(([k,v])=>statNames[k]+' '+(v>0?'+':'')+v.toFixed(1));
 $('interpretation').textContent='Spielauslegung: '+effects.join(' · ')+(world.law_profile.operation?' · '+world.law_profile.operation.party+' auflösen':'')+' / '+world.law_profile.source;
 $('parties').innerHTML=Object.entries(world.parties).map(([p,c])=>`<button data-party="${esc(p)}" style="--pc:${c.color}" class="${partyFilter===p?'active':''}"><span class="p-name">${esc(c.short)}</span><span class="p-count">${world.seats[p]}</span><small>Sitze</small></button>`).join('');
 $('world-stats').innerHTML=Object.entries(world.stats).map(([k,v])=>`<div class="metric"><label>${statNames[k]}</label><strong>${Math.round(v)}</strong><div class="bar"><i style="width:${v}%;background:${v<25?'#ff677d':'#d9fa84'}"></i></div></div>`).join('');
 $('coalition').textContent=world.coalition.length?world.coalition.map(p=>world.parties[p]?.short||p).join(' + '):'KEINE REGIERUNGS-MEHRHEIT';$('cohesion').textContent=Math.round(world.coalition_cohesion)+'%';$('cohesionbar').style.width=world.coalition_cohesion+'%';
 $('ai-status').textContent=world.ai_status;$('ai').checked=world.ai_enabled;
 if(document.activeElement!==$('absurdity'))$('absurdity').value=world.absurdity;
 if(document.activeElement!==$('chaos'))$('chaos').value=world.chaos;
 $('absurdvalue').textContent=world.absurdity+' / 100';$('chaosvalue').textContent=world.chaos.toFixed(2)+'×';
 renderProfile();renderFeed();renderVotes();
 const speaker=world.members.find(m=>m.id===world.speaker);
 const talking=world.members.filter(m=>m.bubble&&m.bubble_until>world.tick);
 const last=world.events.at(-1);
 $('speaker-name').textContent=speaker?`${speaker.name} / ${speaker.party}`:(talking.at(-1)?talking.at(-1).name:'DAS PRÄSIDIUM');
 $('dialogue').textContent=['evakuierung','wahl','ergebnis'].includes(world.phase)?(last?.text||'Sitzung unterbrochen.'):(speaker?.bubble||talking.at(-1)?.bubble||last?.text||'Die Sitzung ist bereit.');
 $('speaker-mark').textContent=speaker?String(speaker.id):'§';
 const major=world.effects.filter(e=>conflictKinds.includes(e.kind)||['goose','blackout','coffee','election_result','vote_result'].includes(e.kind)).at(-1);
 $('event-banner').hidden=!major;if(major)$('event-banner').textContent=major.text;
 lastTick=world.tick;
}
function renderProfile(){const m=world.members.find(m=>m.id===selected)||world.members[0];if(!m)return;selected=m.id;
 $('profileid').textContent='#'+String(m.id).padStart(2,'0');const pc=world.parties[m.party]?.color||'#ddd';
 const metric=(k,label)=>`<div><label>${label}<b>${Math.round(m[k])}</b></label><div class="bar"><i style="width:${m[k]}%;background:${['stress','anger','scandal'].includes(k)?'#fa8796':pc}"></i></div></div>`;
 const axes=['Fortschritt','Ökologie','Sozialstaat','Markt','International','Freiheit','Wachstum'];
 const links=Object.entries(m.relations).sort((a,b)=>Math.abs(b[1])-Math.abs(a[1])).slice(0,3).map(([id,r])=>`${world.members.find(o=>o.id===Number(id))?.name||id}: ${r>0?'+':''}${Math.round(r)}`);
 $('profile').innerHTML=`<div class="portrait" style="--pc:${pc}"><div class="avatar">${esc(m.name.split(' ').map(s=>s[0]).join(''))}</div><span class="id-large">${String(m.id).padStart(2,'0')}</span></div><h3>${esc(m.name)}</h3><p class="party-name"><span style="color:${pc}">●</span> ${esc(m.party)}</p><div class="traits"><span class="tag">${esc(m.personality)}</span><span class="tag">${esc(stateLabels[m.state]||m.state)}</span><span class="tag">Ziel: ${esc(m.goal)}</span></div><div class="profile-metrics">${metric('stress','Stress')}${metric('energy','Energie')}${metric('loyalty','Parteitreue')}${metric('ambition','Ehrgeiz')}${metric('influence','Einfluss')}${metric('scandal','Skandaldruck')}</div><p class="minor">POLITISCHE ACHSEN / SPIELWERTE</p>${m.values.map((v,i)=>`<div class="axis"><label>${axes[i]}</label><div class="axisbar"><i style="left:${v<0?50+v/2:50}%;width:${Math.abs(v)/2}%"></i></div><span>${v>0?'+':''}${v}</span></div>`).join('')}<p class="minor">BEZIEHUNGEN</p><div class="memory">${links.length?links.map(esc).join('<br>'):'Noch keine starken Beziehungen.'}</div><p class="minor">GEDÄCHTNIS / ${m.speeches} REDEN / ${m.deals} DEALS</p>${m.memory.slice(-3).reverse().map(e=>`<div class="memory">${esc(e.text)}<small>T+${e.tick} · ${esc(e.cause)}</small></div>`).join('')||'<div class="memory">Die Geschichte dieser Figur beginnt jetzt.</div>'}${m.vote?`<div class="memory">STIMME: ${esc(m.vote.toUpperCase())}<small>${esc(m.reason)}</small></div>`:''}`;
}
function renderFeed(){const filter=$('filter').value;let events=world.events.slice().reverse();
 if(filter==='conflict')events=events.filter(e=>conflictKinds.includes(e.kind));
 if(filter==='law')events=events.filter(e=>['law','amendment','amendment_result','vote_start','vote_result','session','party_dissolved','interpretation'].includes(e.kind));
 if(filter==='selected')events=events.filter(e=>e.actors.includes(selected));
 if(partyFilter){const ids=world.members.filter(m=>m.party===partyFilter).map(m=>m.id);events=events.filter(e=>e.actors.some(id=>ids.includes(id))||!e.actors.length)}
 const latest=world.events.at(-1)?.id||0;$('eventcount').textContent=latest+' EREIGNISSE';
 if(latest===lastSeq&&$('events').dataset.filter===filter+partyFilter+selected)return;
 lastSeq=latest;$('events').dataset.filter=filter+partyFilter+selected;
 $('events').innerHTML=events.slice(0,60).map(e=>`<article class="event ${conflictKinds.includes(e.kind)?'conflict':''}" data-actor="${e.actors[0]||''}"><div class="event-top"><span class="event-kind">${esc(kindLabels[e.kind]||e.kind)}</span><span>T+${String(e.tick).padStart(4,'0')}</span></div><p>${esc(e.text)}</p>${e.cause?`<small>↳ ${esc(e.cause)}</small>`:''}</article>`).join('')||'<div class="memory">Noch keine Ereignisse für diesen Filter.</div>';
}
function renderVotes(){const v=world.votes;$('voting').hidden=!v;if(!v)return;const c=v.counts,colors={ja:'#d9fa84',nein:'#ff677d',enthalten:'#a6afc3',abwesend:'#44516a'};
 $('voting').innerHTML=`<div class="vote-total">${Object.entries(c).map(([k,n])=>`<span style="color:${colors[k]}"><b>${n}</b>${k}</span>`).join('')}</div><div class="vote-strip">${Object.entries(c).map(([k,n])=>`<i style="width:${n/Math.max(1,Object.values(c).reduce((a,b)=>a+b,0))*100}%;background:${colors[k]}"></i>`).join('')}</div>`;
}
function rect(x,y,w,h,r=8){ctx.beginPath();ctx.roundRect(x,y,w,h,r)}
function text(s,x,y,size=12,color='#a3b1c8',align='center'){ctx.fillStyle=color;ctx.font=`${size}px system-ui`;ctx.textAlign=align;ctx.fillText(s,x,y)}
function figure(x,y,color,scale=1,pose='seated',time=0){ctx.save();ctx.translate(x,y);ctx.scale(scale,scale);
 const bob=['fighting','protesting'].includes(pose)?Math.sin(time*7)*2:0;
 ctx.strokeStyle='#0d1523';ctx.lineWidth=2;ctx.fillStyle=color;
 rect(-7,-1+bob,14,15,4);ctx.fill();ctx.stroke();ctx.beginPath();ctx.arc(0,-7+bob,5.5,0,Math.PI*2);ctx.fillStyle='#d8b49c';ctx.fill();ctx.stroke();
 ctx.strokeStyle=color;ctx.lineWidth=3;ctx.lineCap='round';ctx.beginPath();ctx.moveTo(-6,3+bob);ctx.lineTo(-11,pose==='protesting'?-13:8);ctx.moveTo(6,3+bob);ctx.lineTo(11,pose==='fighting'?-6:8);ctx.stroke();
 ctx.strokeStyle='#697c99';ctx.beginPath();ctx.moveTo(-3,13+bob);ctx.lineTo(-4,20);ctx.moveTo(3,13+bob);ctx.lineTo(4,20);ctx.stroke();ctx.restore();}
function speechBubble(s,x,y,color){const max=120;let lines=[],line='';for(const w of s.split(' ')){if((line+w).length>21){lines.push(line.trim());line=''}line+=w+' '}if(line)lines.push(line.trim());lines=lines.slice(0,4);const width=Math.min(170,Math.max(80,Math.max(...lines.map(s=>s.length))*5.5+18)),height=lines.length*13+13;
 x=Math.max(12,Math.min(canvas.width-width-12,x-width/2));y=Math.max(68,y-height-28);
 ctx.fillStyle='#e3e9f0';rect(x,y,width,height,6);ctx.fill();ctx.strokeStyle=color;ctx.lineWidth=2;ctx.stroke();lines.forEach((l,i)=>text(l,x+width/2,y+16+i*13,10,'#142237'));
}
function draw(now){requestAnimationFrame(draw);const time=now/1000,W=canvas.width,H=canvas.height;ctx.clearRect(0,0,W,H);
 const bg=ctx.createLinearGradient(0,0,0,H);bg.addColorStop(0,'#182235');bg.addColorStop(1,'#101928');ctx.fillStyle=bg;ctx.fillRect(0,0,W,H);
 // Architecture: galleries, concentric floor bands, aisles and rooms.
 ctx.strokeStyle='#26364d';ctx.lineWidth=2;for(let i=0;i<4;i++){ctx.beginPath();ctx.ellipse(W*.5,H*.59,W*(.27+i*.06),H*(.21+i*.035),0,Math.PI,Math.PI*2);ctx.stroke()}
 ctx.fillStyle='#202b3d';rect(28,H*.71,180,110,12);ctx.fill();rect(W-212,H*.71,180,110,12);ctx.fill();
 text('FRAKTIONSFLUR',118,H*.74,10,'#617792');text('HINTERZIMMER',W-122,H*.74,10,'#617792');
 for(let i=0;i<5;i++){ctx.fillStyle='#29364b';rect(53+i*27,H*.78,18,28,4);ctx.fill();rect(W-188+i*27,H*.78,18,28,4);ctx.fill()}
 text('PRESSE / BESUCHERTRIBÜNE',W*.5,45,10,'#5e7391');for(let i=0;i<30;i++){ctx.fillStyle=i%3?'#26374d':'#40516a';ctx.beginPath();ctx.arc(W*.23+i*W*.0185,64,4,0,Math.PI*2);ctx.fill()}
 ctx.strokeStyle='#30405b';ctx.beginPath();ctx.moveTo(W*.22,H*.68);ctx.lineTo(W*.78,H*.68);ctx.stroke();
 ctx.fillStyle='#283951';rect(W*.44,H*.73, W*.12,42,5);ctx.fill();ctx.fillStyle='#4c624a';ctx.fillRect(W*.45,H*.73,W*.1,4);text('REDNERPULT',W*.5,H*.83,10,'#6f829e');
 ctx.fillStyle='#23324b';rect(W*.37,H*.88,W*.26,38,6);ctx.fill();text('PRÄSIDIUM',W*.5,H*.915,10,'#8b9db7');
 if(!world)return;
 const selectedM=world.members.find(m=>m.id===selected);
 const px=m=>m.position[0]*W,py=m=>m.position[1]*H;
 // Empty seats persist when an MP moves or resigns.
 for(const m of world.members){ctx.fillStyle=m.resigned?'#151e2d':'#27364d';rect(m.home[0]*W-9,m.home[1]*H+7,18,14,3);ctx.fill()}
 if($('relations').checked&&selectedM){for(const [id,r]of Object.entries(selectedM.relations)){const o=world.members.find(m=>m.id===+id);if(!o||Math.abs(r)<8)continue;ctx.strokeStyle=r>0?'#79dba765':'#ff677d65';ctx.lineWidth=1+Math.abs(r)/60;ctx.setLineDash(r<0?[4,5]:[]);ctx.beginPath();ctx.moveTo(px(selectedM),py(selectedM));ctx.lineTo(px(o),py(o));ctx.stroke()}ctx.setLineDash([])}
 const visible=world.members.filter(m=>m.position[0]<1.02).slice().sort((a,b)=>a.position[1]-b.position[1]);
 for(const m of visible){let p=positions.get(m.id);if(!p){p=[px(m),py(m)];positions.set(m.id,p)}p[0]+=(px(m)-p[0])*.1;p[1]+=(py(m)-p[1])*.1;
 const color=world.parties[m.party]?.color||'#ccc';ctx.globalAlpha=partyFilter&&m.party!==partyFilter?.28:1;
 if(m.id===selected){ctx.strokeStyle='#d9fa84';ctx.lineWidth=1.5;ctx.beginPath();ctx.ellipse(p[0],p[1]+18,15,6,0,0,Math.PI*2);ctx.stroke()}
 if(m.stress>65){ctx.strokeStyle='#fa647c55';ctx.beginPath();ctx.arc(p[0],p[1],18+Math.sin(time*3)*2,0,Math.PI*2);ctx.stroke()}
 figure(p[0],p[1],color,1,m.state,time);
 if($('votesview').checked&&m.vote){text(m.vote==='ja'?'✓':m.vote==='nein'?'×':m.vote==='enthalten'?'−':'○',p[0]+10,p[1]-9,15,m.vote==='ja'?'#d9fa84':m.vote==='nein'?'#ff677d':'#a6afc3')}
 else text(String(m.id),p[0],p[1]+34,7,'#91a3bc');ctx.globalAlpha=1;
 if(m.state==='protesting'){ctx.fillStyle='#e5dfa8';ctx.fillRect(p[0]-18,p[1]-35,36,17);text('NEIN!',p[0],p[1]-24,8,'#302e1a')}
 if(m.state==='fighting'){text('✦',p[0]+18*Math.sin(time*8),p[1]-22,22,'#ffd18c')}
 }
 const bubbles=world.members.filter(m=>m.bubble&&m.position[0]<1&&(m.id===world.speaker||m.id===selected||m.bubble_until-world.tick>7)).slice(-3);
 for(const m of bubbles)speechBubble(m.bubble,px(m),py(m),world.parties[m.party]?.color||'#ccc');
 for(const e of world.effects){const progress=(world.tick-e.tick)/(e.until-e.tick||1);
  if(e.kind==='brawl'){const a=world.members.find(m=>m.id===e.actors[0]);if(a){figure(px(a)-20,py(a)+30,'#f0c778',1,'seated',time);figure(px(a)+35,py(a)+30,'#f0c778',1,'seated',time);text('SICHERHEIT',px(a),py(a)+65,8,'#f0c778')}}
  if(e.kind==='streaker'){const x=(.05+Math.min(.9,progress*.95))*W,y=H*.66+Math.sin(time*3)*25;figure(x,y,'#e7bda7',1.15,'protesting',time);text('FLITZER',x,y-30,9,'#ffc877');figure(x-55,y,'#f0c778',1,'fighting',time);figure(x-83,y+10,'#f0c778',1,'fighting',time)}
  if(e.kind==='goose'){text('🪿',W*.5,H*.72,40,'#fff');text('HONK!',W*.5+43,H*.7,12,'#ffc877')}
  if(e.kind==='confetti'||e.kind==='election_result'){for(let i=0;i<70;i++){ctx.fillStyle=['#d9fa84','#ff677d','#79dba7','#53b4ed'][i%4];let x=(Math.sin(i*7.3)*.5+.5)*W,y=(time*80+i*31)%H;ctx.fillRect(x,y,5,7)}}
  if(e.kind==='coffee'){text('☕ ×',118,H*.81,30,'#ffbc80')}
  if(e.kind==='blackout'){ctx.fillStyle='#000b';ctx.fillRect(0,0,W,H);for(let i=0;i<8;i++){ctx.fillStyle='#fff9';ctx.beginPath();ctx.arc(W*(.2+i*.08),H*.4,4,0,Math.PI*2);ctx.fill()}}
 }
 if(world.phase==='evakuierung'){ctx.strokeStyle='#eaaa57';ctx.setLineDash([7,5]);ctx.beginPath();ctx.moveTo(W*.15,H*.67);ctx.lineTo(W*.87,H*.67);ctx.stroke();ctx.setLineDash([]);text('SAAL GERÄUMT / SICHERHEITSDIENST',W*.5,H*.61,16,'#f2c880');figure(W*.2,H*.68,'#f0c778',1.2);figure(W*.8,H*.68,'#f0c778',1.2)}
 if(world.phase==='wahl'){ctx.fillStyle='#243346eb';rect(W*.32,H*.36,W*.36,H*.24,12);ctx.fill();text('NEUWAHL',W*.5,H*.43,26,'#d9fa84');text('Mandate werden neu verteilt.',W*.5,H*.48,13,'#c3cee0');text('▣',W*.5,H*.56,38,'#d9fa84')}
 text('SATIRISCHE SPIELWELT / KEINE REALEN PERSONEN',W*.5,H-14,8,'#556882');
 if(mouse){const m=world.members.find(m=>Math.hypot(px(m)-mouse.x,py(m)-mouse.y)<18);if(m){const x=Math.min(W-170,mouse.x+15),y=Math.max(10,mouse.y-32);ctx.fillStyle='#0b101de8';rect(x,y,165,40,4);ctx.fill();text(m.name,x+8,y+15,10,'#eee','left');text(m.party,x+8,y+30,9,'#a6b5ca','left')}}
}
canvas.addEventListener('click',e=>{if(!world)return;const r=canvas.getBoundingClientRect(),x=(e.clientX-r.left)/r.width*canvas.width,y=(e.clientY-r.top)/r.height*canvas.height;const m=world.members.slice().sort((a,b)=>Math.hypot(a.position[0]*canvas.width-x,a.position[1]*canvas.height-y)-Math.hypot(b.position[0]*canvas.width-x,b.position[1]*canvas.height-y))[0];if(m&&Math.hypot(m.position[0]*canvas.width-x,m.position[1]*canvas.height-y)<28){selected=m.id;renderProfile();lastSeq=-1;renderFeed()}});
canvas.addEventListener('mousemove',e=>{const r=canvas.getBoundingClientRect();mouse={x:(e.clientX-r.left)/r.width*canvas.width,y:(e.clientY-r.top)/r.height*canvas.height}});canvas.addEventListener('mouseleave',()=>mouse=null);
$('run').onclick=()=>control({action:world?.running?'pause':'run'});$('step').onclick=()=>control({action:'step'});
$('lawform').onsubmit=async e=>{e.preventDefault();if(await control({action:'law',text:$('law').value}))toast('Entwurf eingebracht. Die Figuren entscheiden selbst.')};
$('parties').onclick=e=>{const b=e.target.closest('button[data-party]');if(b){partyFilter=partyFilter===b.dataset.party?null:b.dataset.party;render();}};
$('events').onclick=e=>{const a=e.target.closest('[data-actor]');if(a&&+a.dataset.actor){selected=+a.dataset.actor;renderProfile();if($('filter').value==='selected'){lastSeq=-1;renderFeed()}}};
$('filter').onchange=()=>{lastSeq=-1;renderFeed()};
function download(url){const a=document.createElement('a');a.href=url;a.download='';a.click()}
$('save').onclick=()=>{download('/api/save');toast('Spielstand wird heruntergeladen. Bewahre die JSON-Datei auf.')};$('history').onclick=()=>download('/api/history');$('load').onclick=()=>$('loadfile').click();
$('loadfile').onchange=async()=>{const f=$('loadfile').files[0];if(!f)return;if(f.size>2000000)return toast('Spielstand ist zu groß.',true);try{if(await control({action:'load',save:JSON.parse(await f.text())})){positions.clear();toast('Spielstand geladen. Die Welt ist pausiert.')}}catch(e){toast('Ungültige JSON-Datei.',true)}$('loadfile').value=''};
for(const id of ['speed','absurdity','chaos']){$(id).oninput=()=>{$('speedvalue').textContent=$('speed').value+'×';$('absurdvalue').textContent=$('absurdity').value+' / 100';$('chaosvalue').textContent=Number($('chaos').value).toFixed(2)+'×'};$(id).onchange=()=>control({action:'settings',speed:+$('speed').value,absurdity:+$('absurdity').value,chaos:+$('chaos').value})}
$('ai').onchange=()=>control({action:'settings',ai:$('ai').checked});
$('interventions').onclick=e=>{const b=e.target.closest('[data-kind]');if(!b)return;const kind=b.dataset.kind;const m=world?.members.find(m=>m.id===selected);let target=world?.members.filter(o=>o.id!==selected&&!o.resigned&&o.ban_until<=world.tick).sort((a,b)=>(m?.relations[String(a.id)]||0)-(m?.relations[String(b.id)]||0))[0]?.id;control({action:'intervene',kind,actor:selected,target,sandbox:true})};
$('reset').onclick=async()=>{if(!confirm('Neue Welt starten? Nicht gespeicherter Fortschritt geht verloren.'))return;if(await control({action:'reset',seed:+$('seed').value})){selected=1;partyFilter=null;positions.clear();toast('Neue Welt ist bereit.')}};
// Follow highlights an active actor's profile, never changes user selection.
setInterval(()=>{if(world&&$('follow').checked&&world.speaker&&document.activeElement?.tagName!=='INPUT'){selected=world.speaker;renderProfile()}},3500);
(async()=>{try{token=(await(await fetch('/api/token')).json()).token;await poll();setInterval(poll,600)}catch(e){toast('Serververbindung fehlgeschlagen.',true)}})();
requestAnimationFrame(draw);
