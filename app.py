from concurrent.futures import ThreadPoolExecutor,as_completed
import hashlib
import streamlit as st
from docx import Document
from pypdf import PdfReader
from ai_engine import AIEngine
from domain import clean_text,duplicate_key,profile_key,unique,vacancy_hash
from sources import SourceManager,JobPostingImporter
from storage import Storage
st.set_page_config(page_title='Loopbaan-Agent 3.0.4',page_icon='🧭',layout='wide')
st.markdown('<style>@media(max-width:768px){div[data-testid="stHorizontalBlock"]{flex-direction:column}div[data-testid="column"]{width:100%!important;flex:1 1 100%!important}}</style>',unsafe_allow_html=True)
D={'profile_text':'','career_move':'Ik zoek een volgende stap waarin mijn brede ervaring betekenisvol kan worden ingezet. De werkelijke opdracht en maatschappelijke opgave zijn belangrijker dan een bekende functietitel.','dna':None,'strategy':None,'results':[],'diagnostics':{},'location':'Boxtel','radius':40,'per_term':5,'max_terms':6,'max_matches':15,'minimum_score':55,'vacancy_file_hash':'','vacancy_file_text':'','vacancy_title':'','vacancy_org':'','vacancy_location':'','vacancy_metadata':None}
for k,v in D.items():
    if k not in st.session_state:st.session_state[k]=v
store=Storage();store.initialize();ai=AIEngine();manager=SourceManager();importer=JobPostingImporter()
def read_upload(f):
    n=f.name.lower()
    if n.endswith('.pdf'):return clean_text('\n'.join(p.extract_text() or '' for p in PdfReader(f).pages))
    if n.endswith('.docx'):return clean_text('\n'.join(p.text for p in Document(f).paragraphs))
    return clean_text(f.read().decode('utf-8',errors='ignore'))
def fb_summary(items):
    pos=[];neg=[];notes=[]
    for i in items:
        (pos if i.get('judgement')=='goede match' else neg).append(i.get('reason',''))
        if i.get('note','').strip():notes.append(i['note'].strip())
    return {'positieve_voorkeuren':unique(pos),'afwijzingsredenen':unique(neg),'toelichtingen':notes[-10:],'aantal':len(items)}
def terms(strategy,limit):
    grouped={}
    for r in strategy.get('roltypen',[]):grouped.setdefault(r.get('categorie','anders'),[]);grouped[r.get('categorie','anders')]+=r.get('zoektermen',[])
    order=['leidinggevend','adviserend','regisserend','programmatisch','netwerkgericht','veranderkundig','bedrijfsvoering','anders'];out=[]
    for x in range(4):
        for c in order:
            vals=unique(grouped.get(c,[]))
            if x<len(vals):out.append(vals[x])
    return unique(out)[:limit]

def animation_words():
    dna = st.session_state.dna or {}
    values = (
        dna.get("maatschappelijke_opgaven", [])
        + dna.get("overdraagbare_competenties", [])
        + dna.get("drijfveren", [])
        + dna.get("waarden", [])
    )
    words = []
    for value in values:
        text = str(value).strip()
        if text and text.lower() not in {w.lower() for w in words}:
            words.append(text)
    return words[:10] or [
        "maatschappelijke opgave",
        "overdraagbaarheid",
        "verbinding",
        "betekenis",
    ]


def search_animation_html(words):
    pills = "".join(
        f'<span class="dna-word" style="--i:{index}">{word}</span>'
        for index, word in enumerate(words)
    )
    return f"""
    <style>
      .search-animation {{
        position: relative;
        min-height: 155px;
        overflow: hidden;
        border: 1px solid rgba(128,128,128,.22);
        border-radius: 18px;
        padding: 20px;
        background:
          radial-gradient(circle at 25% 30%, rgba(99,102,241,.15), transparent 38%),
          radial-gradient(circle at 75% 65%, rgba(16,185,129,.13), transparent 40%);
      }}
      .search-core {{
        position: absolute;
        left: 50%;
        top: 50%;
        width: 58px;
        height: 58px;
        transform: translate(-50%, -50%);
        border-radius: 50%;
        display: grid;
        place-items: center;
        font-size: 29px;
        background: rgba(255,255,255,.88);
        box-shadow: 0 0 0 0 rgba(99,102,241,.34);
        animation: pulse 1.8s infinite;
      }}
      .dna-word {{
        position: absolute;
        left: 50%;
        top: 50%;
        max-width: 170px;
        padding: 7px 11px;
        border-radius: 999px;
        font-size: .82rem;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        background: rgba(255,255,255,.84);
        border: 1px solid rgba(128,128,128,.20);
        animation: orbit 7s linear infinite;
        animation-delay: calc(var(--i) * -0.7s);
      }}
      .search-caption {{
        position: absolute;
        left: 0;
        right: 0;
        bottom: 10px;
        text-align: center;
        font-size: .84rem;
        opacity: .72;
      }}
      @keyframes orbit {{
        from {{
          transform: translate(-50%,-50%) rotate(calc(var(--i) * 42deg))
                     translateX(88px) rotate(calc(var(--i) * -42deg));
        }}
        to {{
          transform: translate(-50%,-50%) rotate(calc(var(--i) * 42deg + 360deg))
                     translateX(88px) rotate(calc(var(--i) * -42deg - 360deg));
        }}
      }}
      @keyframes pulse {{
        0% {{ box-shadow: 0 0 0 0 rgba(99,102,241,.32); }}
        70% {{ box-shadow: 0 0 0 22px rgba(99,102,241,0); }}
        100% {{ box-shadow: 0 0 0 0 rgba(99,102,241,0); }}
      }}
      @media (prefers-reduced-motion: reduce) {{
        .dna-word, .search-core {{ animation: none; }}
      }}
    </style>
    <div class="search-animation">
      {pills}
      <div class="search-core">🧭</div>
      <div class="search-caption">
        Loopbaan-DNA verkent bronnen, opdrachten en onverwachte verbindingen
      </div>
    </div>
    """


def card(index,item):
    v=item['vacancy'];m=item['match'];s=m.get('totaalscore') or 0;icon='🟢' if s>=75 else '🟡' if s>=60 else '🟠'
    with st.container(border=True):
        st.markdown(f"### {icon} {s} — {v['title']}");st.caption(f"{v['organisation']} · {v['location']} · Bron: {v['source']} · {m['classificatie']}")
        if m.get('titel_is_misleidend'):st.info('De feitelijke opdracht past beter dan de functietitel doet vermoeden.')
        c=st.columns(5);c[0].metric('Opdracht',m.get('opdrachtmatch'));c[1].metric('Bewijs',m.get('bewijsuit_ervaring'));c[2].metric('Overdracht',m.get('overdraagbaarheid'));c[3].metric('Context',m.get('contextmatch'));c[4].metric('Ontwikkeling',m.get('ontwikkelpotentieel'))
        st.write(m.get('belangrijkste_argument',''));st.markdown('**Brugredenering**');st.write(m.get('brugredenering',''))
        if m.get('belangrijkste_risico'):st.warning(m['belangrijkste_risico'])
        if v.get('url'):st.markdown(f'<a href="{v["url"]}" target="_blank">Bekijk vacature ↗</a>',unsafe_allow_html=True)
        if st.button('💬 Coachadvies',key=f'coach_{index}'):
            item['coach']=ai.coach(st.session_state.dna,v,m);st.session_state.results[index]=item;st.rerun()
        if item.get('coach'):st.success(item['coach'])
        with st.expander('Feedback'):
            j=st.radio('Oordeel',['goede match','geen goede match'],horizontal=True,key=f'j_{index}');r=st.selectbox('Reden',['maatschappelijke opgave','opdracht past','overdraagbaarheid','verrassende brugrol','te specialistisch','te veel personeelsverantwoordelijkheid','te weinig senioriteit','voorwaarden','locatie','anders'],key=f'r_{index}');n=st.text_input('Toelichting',key=f'n_{index}')
            if st.button('Feedback opslaan',key=f's_{index}'):
                store.add_feedback(profile_key(st.session_state.profile_text,st.session_state.career_move),v,j,r,n);st.success('Feedback opgeslagen.')
st.title('🧭 Loopbaan-Agent 3.0.4');st.caption('Multi-source zoeken vanuit Loopbaan-DNA, maatschappelijke opgaven en roltypen — met Adzuna, Jooble en je eigen bibliotheek.')
t1,t2,t3,t4,t5=st.tabs(['1. Loopbaan-DNA','2. Opportunity-strategie','3. Zoeken','4. Bibliotheek','5. Feedback'])
with t1:
    up=st.file_uploader('Upload cv en/of profielschets',type=['pdf','docx','txt'],accept_multiple_files=True)
    if up:st.session_state.profile_text='\n\n--- DOCUMENT ---\n\n'.join(read_upload(f) for f in up);st.success(f'{len(up)} bestand(en) ingelezen.')
    st.session_state.profile_text=st.text_area('Profieltekst',value=st.session_state.profile_text,height=260);st.session_state.career_move=st.text_area('Welke beweging wil je maken?',value=st.session_state.career_move,height=120)
    k=profile_key(st.session_state.profile_text,st.session_state.career_move);cached=store.get_profile(k)
    if cached and st.session_state.dna is None:st.session_state.dna=cached
    if st.button('🧬 Maak of vernieuw Loopbaan-DNA',type='primary',disabled=not st.session_state.profile_text.strip()):
        with st.spinner('Loopbaan-DNA wordt opgebouwd...'):d=ai.build_dna(st.session_state.profile_text,st.session_state.career_move);store.save_profile(k,d);st.session_state.dna=d;st.session_state.strategy=None;st.session_state.results=[]
        st.rerun()
    if st.session_state.dna:
        d=st.session_state.dna;st.subheader('Professionele kern');st.write(d.get('samenvatting',''));c=st.columns(3)
        with c[0]:st.markdown('**Drijfveren en waarden**');st.markdown('\n'.join(f'- {x}' for x in d.get('drijfveren',[])+d.get('waarden',[])))
        with c[1]:st.markdown('**Overdraagbare competenties**');st.markdown('\n'.join(f'- {x}' for x in d.get('overdraagbare_competenties',[])))
        with c[2]:st.markdown('**Maatschappelijke opgaven**');st.markdown('\n'.join(f'- {x}' for x in d.get('maatschappelijke_opgaven',[])))
with t2:
    if not st.session_state.dna:st.info('Maak eerst een Loopbaan-DNA.')
    else:
        k=profile_key(st.session_state.profile_text,st.session_state.career_move);cached=store.get_strategy(k)
        if cached and st.session_state.strategy is None:st.session_state.strategy=cached
        if st.button('🗺️ Maak opportunity-strategie',type='primary'):
            with st.spinner('Opgaven en roltypen worden verkend...'):s=ai.build_strategy(st.session_state.dna,fb_summary(store.get_feedback(k)));store.save_strategy(k,s);st.session_state.strategy=s
            st.rerun()
        if st.session_state.strategy:
            for x in st.session_state.strategy.get('opgavegebieden',[]):
                with st.container(border=True):st.markdown(f"### {x['naam']}");st.write(x['waarom']);st.caption('Signalen: '+', '.join(x['signalen']))
            st.subheader('Roltypen')
            for r in st.session_state.strategy.get('roltypen',[]):
                with st.expander(f"{r['naam']} · {r['categorie']}"):st.write(r['brugredenering']);st.caption('Zoektermen: '+', '.join(r['zoektermen']))
with t3:
    if not st.session_state.dna or not st.session_state.strategy:st.info('Maak eerst Loopbaan-DNA en opportunity-strategie.')
    else:
        av=[x.name for x in manager.available()];enabled=st.multiselect('Actieve externe bronnen',av,default=av);c=st.columns(3)
        with c[0]:st.session_state.location=st.text_input('Locatie',value=st.session_state.location)
        with c[1]:st.session_state.radius=st.number_input('Straal (km)',5,200,int(st.session_state.radius),5)
        with c[2]:st.session_state.minimum_score=st.number_input('Minimumscore sterke match',0,100,int(st.session_state.minimum_score),5)
        c=st.columns(3)
        with c[0]:st.session_state.per_term=st.number_input('Vacatures per term en bron',3,20,int(st.session_state.per_term),1)
        with c[1]:st.session_state.max_terms=st.number_input('Maximaal zoektermen',3,20,int(st.session_state.max_terms),1)
        with c[2]:st.session_state.max_matches=st.number_input('Maximaal AI-beoordelingen',5,50,int(st.session_state.max_matches),5)
        depth = st.radio(
            'Zoekdiepte',
            ['Snel', 'Normaal', 'Grondig'],
            index=1,
            horizontal=True,
            help='Snel gebruikt minder zoektermen en AI-beoordelingen. Grondig duurt duidelijk langer.'
        )
        cc1, cc2 = st.columns([2, 1])
        with cc2:
            if st.button('♻️ Zoekcache wissen'):
                st.cache_data.clear()
                st.success('Zoekcache gewist.')
        if st.button('🔎 Zoek kansen',type='primary'):
            k = profile_key(
                st.session_state.profile_text,
                st.session_state.career_move
            )
            summary = fb_summary(store.get_feedback(k))

            depth_settings = {
                'Snel': {'terms': 3, 'matches': 10},
                'Normaal': {
                    'terms': min(6, int(st.session_state.max_terms)),
                    'matches': min(15, int(st.session_state.max_matches))
                },
                'Grondig': {
                    'terms': int(st.session_state.max_terms),
                    'matches': int(st.session_state.max_matches)
                },
            }
            chosen = depth_settings[depth]
            ts = terms(st.session_state.strategy, chosen['terms'])

            animation = st.empty()
            animation.markdown(
                search_animation_html(animation_words()),
                unsafe_allow_html=True
            )

            prog = st.progress(0.03, text='Zoekstrategie voorbereiden…')
            status = st.status(
                'Loopbaan-Agent zoekt kansen',
                expanded=True
            )

            try:
                status.write(
                    f'{len(ts)} zoektermen verdeeld over '
                    f'{len(enabled)} actieve bron(nen).'
                )
                prog.progress(0.10, text='Vacaturebronnen raadplegen…')

                external, diag = manager.search(
                    ts,
                    st.session_state.location,
                    int(st.session_state.radius),
                    int(st.session_state.per_term),
                    enabled
                )

                library = store.get_vacancies()
                diag['Bibliotheek'] = {
                    'gevonden': len(library),
                    'status': 'gereed',
                    'zoektermen_gebruikt': 0,
                    'fouten': []
                }

                source_total = len(external)
                status.write(
                    f'Externe bronnen leverden {source_total} resultaten; '
                    f'de bibliotheek bevat {len(library)} vacature(s).'
                )
                prog.progress(0.30, text='Dubbele vacatures verwijderen…')

                allv = external + library
                before = len(allv)
                um = {}

                for v in allv:
                    dk = duplicate_key(v)
                    if (
                        dk not in um
                        or len(v['description']) > len(um[dk]['description'])
                    ):
                        um[dk] = v

                uv = list(um.values())
                duplicate_count = before - len(uv)

                signals = unique([
                    signal
                    for opportunity in st.session_state.strategy.get(
                        'opgavegebieden', []
                    )
                    for signal in opportunity.get('signalen', [])
                ])

                def local(v):
                    text = (
                        v['title'] + ' ' + v['description'] + ' '
                        + v['organisation']
                    ).lower()
                    return (
                        sum(2 for signal in signals if signal.lower() in text)
                        + (1 if v['description'] else 0)
                    )

                candidate_limit = chosen['matches']
                cand = sorted(
                    uv,
                    key=local,
                    reverse=True
                )[:candidate_limit]

                status.write(
                    f'{len(uv)} unieke vacatures; {duplicate_count} dubbelen '
                    f'verwijderd; {len(cand)} geselecteerd voor beoordeling.'
                )

                matches = {}
                unc = []

                for v in cand:
                    m = store.get_match(k, vacancy_hash(v))
                    matches[v['id']] = m if m else None
                    if not m:
                        unc.append(v)

                if not cand:
                    st.session_state.results = []
                    st.session_state.diagnostics = {
                        **diag,
                        'Totaal voor ontdubbelen': before,
                        'Dubbelen verwijderd': duplicate_count,
                        'Uniek': len(uv),
                        'Naar Matcher': 0,
                        'Matcherfouten': [],
                    }
                    prog.progress(1.0, text='Klaar — geen vacatures gevonden')
                    status.update(
                        label='Geen vacatures gevonden',
                        state='error',
                        expanded=True
                    )
                    st.warning(
                        'De bronnen leverden geen bruikbare vacatures. '
                        'Open Zoekdiagnostiek om per bron te zien wat er gebeurde.'
                    )
                else:
                    batches = [
                        unc[i:i + 5] for i in range(0, len(unc), 5)
                    ]
                    done = 0
                    matcher_errors = []
                    dna = st.session_state.dna
                    strategy = st.session_state.strategy

                    def assess(batch):
                        return batch, AIEngine().match_batch(
                            dna,
                            strategy,
                            summary,
                            batch
                        )

                    if unc:
                        prog.progress(
                            0.45,
                            text=f'Matcher beoordeelt {len(unc)} nieuwe vacatures…'
                        )
                        status.write(
                            f'{len(cand) - len(unc)} beoordeling(en) uit cache; '
                            f'{len(unc)} nieuwe beoordeling(en).'
                        )

                        with ThreadPoolExecutor(max_workers=2) as ex:
                            future_map = {
                                ex.submit(assess, batch): batch
                                for batch in batches
                            }

                            for future in as_completed(future_map):
                                batch = future_map[future]
                                try:
                                    returned_batch, ms = future.result()
                                    done += len(returned_batch)
                                    progress_value = (
                                        0.45
                                        + 0.48
                                        * done / max(len(unc), 1)
                                    )
                                    prog.progress(
                                        min(0.93, progress_value),
                                        text=(
                                            f'Matcher heeft {done} van '
                                            f'{len(unc)} nieuwe vacatures beoordeeld'
                                        )
                                    )

                                    by = {
                                        match['id']: match for match in ms
                                    }
                                    for v in returned_batch:
                                        if v['id'] in by:
                                            matches[v['id']] = by[v['id']]
                                            store.save_match(
                                                k,
                                                vacancy_hash(v),
                                                by[v['id']]
                                            )
                                except Exception:
                                    matcher_errors.append(
                                        f'Een batch van {len(batch)} vacatures '
                                        'kon niet worden beoordeeld.'
                                    )
                    else:
                        status.write(
                            'Alle geselecteerde vacatures zijn uit de cache geladen.'
                        )

                    results = []
                    for v in cand:
                        m = matches.get(v['id'])
                        if not m:
                            continue
                        score = m.get('totaalscore') or 0
                        group = (
                            'sterk'
                            if score >= st.session_state.minimum_score
                            else (
                                'mogelijk'
                                if score >= max(
                                    40,
                                    st.session_state.minimum_score - 15
                                )
                                else 'lager'
                            )
                        )
                        results.append({
                            'vacancy': v,
                            'match': m,
                            'group': group,
                            'coach': None
                        })

                    results.sort(
                        key=lambda x: -(
                            x['match'].get('totaalscore') or 0
                        )
                    )
                    st.session_state.results = results
                    st.session_state.diagnostics = {
                        **diag,
                        'Totaal voor ontdubbelen': before,
                        'Dubbelen verwijderd': duplicate_count,
                        'Uniek': len(uv),
                        'Naar Matcher': len(cand),
                        'Beoordeeld': len(results),
                        'Matcherfouten': matcher_errors,
                    }

                    prog.progress(1.0, text='Klaar')
                    if results:
                        status.update(
                            label=(
                                f'Zoekactie afgerond — '
                                f'{len(results)} vacatures beoordeeld'
                            ),
                            state='complete',
                            expanded=False
                        )
                    else:
                        status.update(
                            label='Zoekactie afgerond zonder beoordelingen',
                            state='error',
                            expanded=True
                        )
                        st.warning(
                            'Er zijn vacatures gevonden, maar de Matcher leverde '
                            'geen bruikbare beoordelingen. Bekijk Zoekdiagnostiek.'
                        )
            except Exception:
                prog.progress(1.0, text='Zoekactie gestopt')
                status.update(
                    label='Zoekactie kon niet worden afgerond',
                    state='error',
                    expanded=True
                )
                st.error(
                    'De zoekactie is onverwacht gestopt. API-sleutels en '
                    'technische URL’s worden bewust niet getoond. '
                    'Probeer de stand Snel of wis de zoekcache.'
                )
            finally:
                animation.empty()
        if st.session_state.diagnostics:
            with st.expander('Zoekdiagnostiek', expanded=True):
                diagnostics = st.session_state.diagnostics
                for source_name in ['Adzuna', 'Jooble', 'Bibliotheek']:
                    source = diagnostics.get(source_name)
                    if not isinstance(source, dict):
                        continue
                    found = source.get('gevonden', 0)
                    status = source.get('status', 'gereed')
                    st.markdown(f'**{source_name}: {found} vacatures · {status}**')
                    used = source.get('zoektermen_gebruikt')
                    if used is not None:
                        st.caption(f'{used} zoektermen gebruikt')
                    for error in source.get('fouten', []):
                        st.warning(error)

                c = st.columns(4)
                c[0].metric('Voor ontdubbelen', diagnostics.get('Totaal voor ontdubbelen', 0))
                c[1].metric('Dubbelen verwijderd', diagnostics.get('Dubbelen verwijderd', 0))
                c[2].metric('Unieke vacatures', diagnostics.get('Uniek', 0))
                c[3].metric('Naar Matcher', diagnostics.get('Naar Matcher', 0))
                assessed = diagnostics.get('Beoordeeld')
                if assessed is not None:
                    st.caption(f'Door Matcher beoordeeld: {assessed}')
                for error in diagnostics.get('Matcherfouten', []):
                    st.warning(error)
        groups=[('Sterke matches','sterk',False),('Mogelijk interessant','mogelijk',True),('Lager beoordeeld','lager',False)]
        for title,g,expanded in groups:
            vals=[(i,x) for i,x in enumerate(st.session_state.results) if x['group']==g]
            if g=='sterk':
                st.subheader(f'{title} ({len(vals)})')
                if vals:
                    [card(i,x) for i,x in vals]
                else:
                    st.caption('Geen vacatures in deze categorie.')
            else:
                with st.expander(f'{title} ({len(vals)})',expanded=expanded):
                    if vals:
                        [card(i,x) for i,x in vals]
                    else:
                        st.caption('Geen vacatures in deze categorie.')
with t4:
    st.subheader('Vacature importeren');url=st.text_input('Vacaturelink')
    if st.button('Importeer vacaturelink',disabled=not url.strip()):
        try:v=importer.import_url(url.strip());store.save_vacancy(v);st.success('Vacature opgeslagen.')
        except Exception as e:st.error(str(e))
    up=st.file_uploader('Of upload PDF, DOCX of TXT',type=['pdf','docx','txt'],key='vu')
    if up:
        file_hash=hashlib.sha256(up.getvalue()).hexdigest()
        if file_hash!=st.session_state.vacancy_file_hash:
            with st.spinner('Functietitel en organisatie worden uitgelezen...'):
                text=read_upload(up)
                metadata=ai.extract_vacancy_metadata(text,up.name)
                st.session_state.vacancy_file_hash=file_hash
                st.session_state.vacancy_file_text=text
                st.session_state.vacancy_metadata=metadata
                st.session_state.vacancy_title=metadata.get('functietitel') or up.name.rsplit('.',1)[0]
                st.session_state.vacancy_org=metadata.get('organisatie','')
                st.session_state.vacancy_location=metadata.get('locatie','')

        metadata=st.session_state.vacancy_metadata or {}
        confidence=metadata.get('zekerheid','laag')
        if confidence=='hoog':st.success('Vacaturegegevens automatisch uitgelezen.')
        elif confidence=='middel':st.info('Vacaturegegevens uitgelezen. Controleer ze voor het opslaan.')
        else:st.warning('Niet alle vacaturegegevens konden betrouwbaar worden vastgesteld. Controleer of vul ze aan.')
        if metadata.get('waarschuwing'):st.caption(metadata['waarschuwing'])

    title=st.text_input('Functietitel',key='vacancy_title')
    org=st.text_input('Organisatie',key='vacancy_org')
    vacancy_location=st.text_input('Locatie',key='vacancy_location')

    if up and st.button('Lees gegevens opnieuw uit'):
        with st.spinner('Vacaturegegevens opnieuw uitlezen...'):
            text=read_upload(up)
            metadata=ai.extract_vacancy_metadata(text,up.name)
            st.session_state.vacancy_file_text=text
            st.session_state.vacancy_metadata=metadata
            st.session_state.vacancy_title=metadata.get('functietitel') or up.name.rsplit('.',1)[0]
            st.session_state.vacancy_org=metadata.get('organisatie','')
            st.session_state.vacancy_location=metadata.get('locatie','')
        st.rerun()

    if up and st.button('Sla vacaturebestand op',type='primary'):
        text=st.session_state.vacancy_file_text or read_upload(up)
        v={'id':'file:'+vacancy_hash({'title':title,'organisation':org,'location':vacancy_location,'description':text})[:16],'title':title or up.name.rsplit('.',1)[0],'organisation':org,'location':vacancy_location,'description':text,'url':'','source':'Bestandsimport'}
        store.save_vacancy(v)
        st.success('Vacature opgeslagen.')
    st.subheader('Persoonlijke vacaturebibliotheek')
    for v in store.get_vacancies():
        with st.container(border=True):st.markdown(f"**{v['title']}**");st.caption(f"{v['organisation']} · Bron: {v['source']}");
        if st.button('Verwijder',key='del_'+v['id']):store.delete_vacancy(v['id']);st.rerun()
with t5:
    k=profile_key(st.session_state.profile_text,st.session_state.career_move);items=store.get_feedback(k);s=fb_summary(items);c=st.columns(3);c[0].metric('Beoordelingen',s['aantal']);c[1].metric('Positieve voorkeuren',len(s['positieve_voorkeuren']));c[2].metric('Afwijzingsredenen',len(s['afwijzingsredenen']));st.subheader('Je waardeert vaker');st.write(' · '.join(s['positieve_voorkeuren']) or 'Nog onvoldoende feedback.');st.subheader('Je haakt vaker af op');st.write(' · '.join(s['afwijzingsredenen']) or 'Nog onvoldoende feedback.')
    for i in items:
        with st.container(border=True):st.markdown(f"**{i['judgement']} — {i['title']}**");st.caption(f"{i['organisation']} · {i['reason']}");st.write(i.get('note',''))
