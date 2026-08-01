import json, anthropic, streamlit as st
from domain import normalize_dna, normalize_strategy, normalize_match
S={'type':'array','items':{'type':'string'}}
DNA={'type':'object','properties':{
'professionele_kern':{'type':'string'},'drijfveren':S,'waarden':S,'ervaringsdomeinen':S,'resultaten':S,'overdraagbare_competenties':S,'bewijsregels':S,'werkstijl':S,'gewenste_beweging':S,'meer_van':S,'minder_van':S,'harde_grenzen':S,'maatschappelijke_opgaven':S,'organisatiecontexten':S,'aannames':S,'samenvatting':{'type':'string'}},'required':['professionele_kern','drijfveren','waarden','ervaringsdomeinen','resultaten','overdraagbare_competenties','bewijsregels','werkstijl','gewenste_beweging','meer_van','minder_van','harde_grenzen','maatschappelijke_opgaven','organisatiecontexten','aannames','samenvatting']}
STRATEGY={'type':'object','properties':{
'opgavegebieden':{'type':'array','items':{'type':'object','properties':{'naam':{'type':'string'},'waarom':{'type':'string'},'signalen':S},'required':['naam','waarom','signalen']}},
'roltypen':{'type':'array','items':{'type':'object','properties':{'naam':{'type':'string'},'categorie':{'type':'string','enum':['leidinggevend','adviserend','regisserend','programmatisch','netwerkgericht','veranderkundig','bedrijfsvoering','anders']},'brugredenering':{'type':'string'},'zoektermen':S},'required':['naam','categorie','brugredenering','zoektermen']}},
'organisatiecategorieen':S,'prioriteiten':S},'required':['opgavegebieden','roltypen','organisatiecategorieen','prioriteiten']}

VACANCY_METADATA={'type':'object','properties':{
'functietitel':{'type':'string'},
'organisatie':{'type':'string'},
'locatie':{'type':'string'},
'zekerheid':{'type':'string','enum':['hoog','middel','laag']},
'waarschuwing':{'type':'string'}
},'required':['functietitel','organisatie','locatie','zekerheid','waarschuwing']}

MATCH={'type':'object','properties':{'matches':{'type':'array','maxItems':5,'items':{'type':'object','properties':{
'id':{'type':'string'},'totaalscore':{'type':'integer','minimum':0,'maximum':100},'classificatie':{'type':'string','enum':['logische stap','brugrol','verrassende match','onvoldoende match']},'titel_is_misleidend':{'type':'boolean'},'opdrachtmatch':{'type':'integer','minimum':0,'maximum':100},'bewijsuit_ervaring':{'type':'integer','minimum':0,'maximum':100},'overdraagbaarheid':{'type':'integer','minimum':0,'maximum':100},'contextmatch':{'type':'integer','minimum':0,'maximum':100},'ontwikkelpotentieel':{'type':'integer','minimum':0,'maximum':100},'belangrijkste_argument':{'type':'string'},'belangrijkste_risico':{'type':'string'},'brugredenering':{'type':'string'}},'required':['id','totaalscore','classificatie','titel_is_misleidend','opdrachtmatch','bewijsuit_ervaring','overdraagbaarheid','contextmatch','ontwikkelpotentieel','belangrijkste_argument','belangrijkste_risico','brugredenering']}}},'required':['matches']}

def secret(n,d=None):
    try:return st.secrets[n]
    except Exception:
        if d is not None:return d
        raise KeyError(f'Ontbrekende Streamlit secret: {n}')

class AIEngine:
    def __init__(self):
        self.client=anthropic.Anthropic(api_key=secret('ANTHROPIC_API_KEY'),timeout=75,max_retries=2)
        self.model=secret('ANTHROPIC_MODEL','claude-haiku-4-5-20251001')
    def tool(self,name,description,schema,system,user,max_tokens):
        r=self.client.messages.create(model=self.model,max_tokens=max_tokens,temperature=0,system=system,tools=[{'name':name,'description':description,'input_schema':schema}],tool_choice={'type':'tool','name':name,'disable_parallel_tool_use':True},messages=[{'role':'user','content':user}])
        for b in r.content:
            if getattr(b,'type',None)=='tool_use' and getattr(b,'name',None)==name and isinstance(getattr(b,'input',None),dict): return b.input
        raise ValueError(f'Tool {name} gaf geen volledig object.')
    def build_dna(self,profile,move):
        return normalize_dna(self.tool('save_dna','Maak een compact Loopbaan-DNA.',DNA,'Je bent een kritische loopbaananalist. Een functietitel is geen identiteit.',f'PROFIEL:\n{profile[:50000]}\n\nGEWENSTE BEWEGING:\n{move}',2200))
    def build_strategy(self,dna,feedback):
        return normalize_strategy(self.tool('save_strategy','Ontwerp opgavegebieden, roltypen en zoektermen.',STRATEGY,'Denk eerst in maatschappelijke opgaven en typen verantwoordelijkheid, pas daarna in titels.',f'LOOPBAAN-DNA:\n{json.dumps(dna,ensure_ascii=False)}\n\nFEEDBACK:\n{json.dumps(feedback,ensure_ascii=False)}\n\nMinimaal 2 leidinggevende, 2 adviserende/regisserende en 1 onverwachte brugrol. Vermijd alleen manager of adviseur als zoekterm.',2200))

    def extract_vacancy_metadata(self,text,filename=''):
        prompt=(
            f"BESTANDSNAAM:\n{filename}\n\n"
            f"VACATURETEKST:\n{text[:18000]}\n\n"
            "Bepaal de officiële functietitel, de wervende organisatie of "
            "werkgever en de primaire werklocatie. Als iets niet betrouwbaar "
            "is vast te stellen, laat het leeg en licht dat kort toe bij "
            "waarschuwing."
        )
        result=self.tool(
            'extract_vacancy_metadata',
            'Lees functietitel, organisatie en locatie uit een vacaturetekst.',
            VACANCY_METADATA,
            'Je leest vacaturemetadata feitelijk uit. Gebruik alleen informatie die in de tekst of bestandsnaam staat. Verzin niets. Verwijder bestandsextensies uit de functietitel.',
            prompt,
            450
        )
        return {
            'functietitel':str(result.get('functietitel') or '').strip(),
            'organisatie':str(result.get('organisatie') or '').strip(),
            'locatie':str(result.get('locatie') or '').strip(),
            'zekerheid':str(result.get('zekerheid') or 'laag').strip(),
            'waarschuwing':str(result.get('waarschuwing') or '').strip()
        }

    def match_batch(self,dna,strategy,feedback,vacancies):
        compact=[{'id':v['id'],'titel':v['title'],'organisatie':v['organisation'],'locatie':v['location'],'bron':v['source'],'omschrijving':v['description'][:4500]} for v in vacancies]
        out=self.tool('save_matches','Beoordeel maximaal vijf vacatures.',MATCH,'Beoordeel de echte opdracht, overdraagbaarheid en context. Vermijd wensdenken.',f'LOOPBAAN-DNA:\n{json.dumps(dna,ensure_ascii=False)}\nSTRATEGIE:\n{json.dumps(strategy,ensure_ascii=False)}\nFEEDBACK:\n{json.dumps(feedback,ensure_ascii=False)}\nVACATURES:\n{json.dumps(compact,ensure_ascii=False)}',1900)
        return [normalize_match(x) for x in out.get('matches',[])]
    def coach(self,dna,vacancy,match):
        r=self.client.messages.create(model=self.model,max_tokens=850,temperature=0,system='Je bent een eerlijke loopbaancoach.',messages=[{'role':'user','content':f'LOOPBAAN-DNA:\n{json.dumps(dna,ensure_ascii=False)}\nVACATURE:\n{json.dumps(vacancy,ensure_ascii=False)}\nMATCH:\n{json.dumps(match,ensure_ascii=False)}\nGeef waarom passend, één positioneringszin, drie gesprekspunten, twee kritische vragen en advies: wel solliciteren, eerst bellen of niet prioriteren.'}])
        text='\n'.join(getattr(b,'text','') for b in r.content if getattr(b,'type',None)=='text').strip()
        if not text: raise ValueError('Coach gaf geen tekst terug.')
        return text
