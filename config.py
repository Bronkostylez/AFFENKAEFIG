"""Seats are official 2025 results. Policy axes are subjective game abstractions."""
AXES=['Fortschritt','Ökologie','Sozialstaat','Markt','International','Freiheit','Wachstum']
PARTIES={
 'CDU':{'short':'CDU','color':'#99a5b9','seats':16,'values':[5,35,5,75,65,20,80]},
 'CSU':{'short':'CSU','color':'#bcc4d1','seats':4,'values':[-10,25,5,70,45,5,80]},
 'AfD':{'short':'AfD','color':'#57baff','seats':15,'values':[-70,-80,-10,65,-80,-25,65]},
 'SPD':{'short':'SPD','color':'#fa647c','seats':12,'values':[55,65,80,-30,70,50,55]},
 'Bündnis 90/Die Grünen':{'short':'GRÜNE','color':'#79dba7','seats':9,'values':[75,95,65,-35,85,80,45]},
 'Die Linke':{'short':'LINKE','color':'#d08afa','seats':6,'values':[70,80,95,-90,45,80,-15]},
 'SSW':{'short':'SSW','color':'#ffc877','seats':1,'values':[65,75,80,-35,85,75,35]},
}
FIRST=['Fridolin','Olafino','Annalotta','Roberto','Alicea','Gregorix','Karla','Wolfram','Sahraline','Kevinchen','Matti','Juli','Bea','Nora','Hansel','Fritzi','Linus','Ronja','Theo','Emilia','Jasper','Maja','Erwin','Luisa','Piet','Nele','Oscar','Minna','Emil','Lotte','Bert','Rudi']
LAST=['Schnolz','Mürz','Bärbockel','Habequark','Weidelino','Gysischnack','Lauterbachling','Klingbeilchen','Wagenrad','Kühnwetter','Sitzkleber','Redeschwall','Mehrheit','Aktenstapel','Zwischenruf','Wendehals','Sofakissen','Stimmzettel','Dauerpause','Quassel','Knallfrosch','Räusper','Tagesordnung','Kaffeekasse','Papierstau','Handzeichen','Saalwacht','Debattino','Wortsalat','Paragraf','Kompromiss','Mikrofon']
PERSONALITIES=['analytisch','konfrontativ','diplomatisch','leidenschaftlich','sarkastisch','pragmatisch','stur','neugierig','charismatisch','pedantisch','spontan','kompromissbereit']
DEFAULT_LAW='Öffentliche Gebäude sollen ihren Energieverbrauch in fünf Jahren deutlich senken.'
MODEL='qwen2.5:7b'
OLLAMA_URL='http://127.0.0.1:11434/api/chat'
WORLD_DEFAULTS={'economy':55.,'ecology':45.,'welfare':50.,'freedom':65.,'trust':60.,'stability':75.,'budget':70.}
ACTIONS=('speech','chat','heckle','deal','protest','brawl','walkout','resign','switch','split','return')
SEAT_SOURCE='https://www.bundeswahlleiterin.de/info/presse/mitteilungen/bundestagswahl-2025/29_25_endgueltiges-ergebnis.html'
POLICY_SOURCES=['https://www.dw.com/de/bundestagswahl-2025-die-parteiprogramme/a-71592905']

OFFICIAL_SEATS={'CDU':164,'CSU':44,'AfD':152,'SPD':120,'Bündnis 90/Die Grünen':85,'Die Linke':64,'SSW':1}

POLICY_SOURCES.append('https://www.ssw.de/fileadmin/user_upload/daten/SSW_Kernforderungen_BTW_2025-net.pdf')
