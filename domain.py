import hashlib, json, re
from typing import Any

def clean_text(v:str)->str:
    seen=set(); out=[]
    for raw in (v or '').replace('\x00',' ').splitlines():
        line=' '.join(raw.split()).strip()
        if line and line.lower() not in seen:
            seen.add(line.lower()); out.append(line)
    return '\n'.join(out)

def normalize_text(v:str)->str: return ' '.join((v or '').lower().split())

def unique(values):
    out=[]; seen=set()
    for v in values or []:
        s=str(v).strip()
        if s and s.lower() not in seen:
            seen.add(s.lower()); out.append(s)
    return out

def ensure_list(v:Any):
    if v is None: return []
    if isinstance(v,list): return unique(v)
    if isinstance(v,str):
        p=[x.strip(' •-\t') for x in re.split(r'\n+|;\s*',v) if x.strip(' •-\t')]
        return unique(p or [v])
    return [str(v)]

def clamp(v):
    try: return max(0,min(100,round(float(v))))
    except (TypeError,ValueError): return None

def profile_key(profile,move): return hashlib.sha256(f'{profile}\n---\n{move}'.encode()).hexdigest()

def vacancy_hash(v):
    raw=json.dumps({k:v.get(k,'') for k in ['title','organisation','location','description']},ensure_ascii=False,sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()

def duplicate_key(v):
    desc=normalize_text(v.get('description',''))[:1200]
    fp=hashlib.sha256(desc.encode()).hexdigest()[:16]
    return '|'.join([normalize_text(v.get('title','')),normalize_text(v.get('organisation','')),normalize_text(v.get('location','')),fp])

def normalize_vacancy(v):
    x={
      'id':str(v.get('id') or vacancy_hash(v)[:16]),'title':str(v.get('title') or '').strip(),
      'organisation':str(v.get('organisation') or '').strip(),'location':str(v.get('location') or '').strip(),
      'description':clean_text(str(v.get('description') or '')),'url':str(v.get('url') or '').strip(),
      'source':str(v.get('source') or 'Onbekend').strip(),'source_detail':str(v.get('source_detail') or '').strip(),
      'salary':str(v.get('salary') or '').strip(),'date_posted':str(v.get('date_posted') or '').strip(),
      'valid_through':str(v.get('valid_through') or '').strip()
    }
    return x

def normalize_dna(d):
    d=dict(d or {})
    for f in ['drijfveren','waarden','ervaringsdomeinen','resultaten','overdraagbare_competenties','bewijsregels','werkstijl','gewenste_beweging','meer_van','minder_van','harde_grenzen','maatschappelijke_opgaven','organisatiecontexten','aannames']:
        d[f]=ensure_list(d.get(f))
    d['professionele_kern']=str(d.get('professionele_kern') or '').strip(); d['samenvatting']=str(d.get('samenvatting') or '').strip()
    return d

def normalize_strategy(d):
    d=dict(d or {})
    d['opgavegebieden']=[{'naam':str(i.get('naam','')).strip(),'waarom':str(i.get('waarom','')).strip(),'signalen':ensure_list(i.get('signalen'))} for i in d.get('opgavegebieden',[]) if isinstance(i,dict)]
    d['roltypen']=[{'naam':str(i.get('naam','')).strip(),'categorie':str(i.get('categorie','')).strip(),'brugredenering':str(i.get('brugredenering','')).strip(),'zoektermen':ensure_list(i.get('zoektermen'))} for i in d.get('roltypen',[]) if isinstance(i,dict)]
    d['organisatiecategorieen']=ensure_list(d.get('organisatiecategorieen')); d['prioriteiten']=ensure_list(d.get('prioriteiten'))
    return d

def normalize_match(i):
    i=dict(i or {})
    for f in ['totaalscore','opdrachtmatch','bewijsuit_ervaring','overdraagbaarheid','contextmatch','ontwikkelpotentieel']: i[f]=clamp(i.get(f))
    for f in ['id','classificatie','belangrijkste_argument','belangrijkste_risico','brugredenering']: i[f]=str(i.get(f) or '')
    i['titel_is_misleidend']=bool(i.get('titel_is_misleidend'))
    return i
