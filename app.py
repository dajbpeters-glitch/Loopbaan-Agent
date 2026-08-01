import streamlit as st

from agents import CoachAgent, ExplorerAgent, LearnerAgent, MatcherAgent, ProfilerAgent
from services import (
    AIClient,
    AdzunaJobSource,
    Database,
    make_profile_hash,
    read_uploaded_files,
    unique_preserve_order,
)

st.set_page_config(
    page_title="Loopbaan-Agent",
    page_icon="🧬",
    layout="wide",
)

DEFAULTS = {
    "profile_text": "",
    "career_move": (
        "Ik zoek een volgende stap waarin mijn brede ervaring betekenisvol kan "
        "worden ingezet. De werkelijke opdracht en maatschappelijke opgave zijn "
        "belangrijker dan een bekende functietitel."
    ),
    "career_dna": None,
    "exploration": None,
    "results": [],
    "match_overview": [],
    "learning_profile": None,
    "location": "Boxtel",
    "radius": 40,
    "jobs_per_term": 10,
    "max_search_terms": 10,
    "max_ai_matches": 25,
    "minimum_score": 55,
}

for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value

db = Database("baanmatchmaker.db")
db.initialize()

ai = AIClient()
profiler = ProfilerAgent(ai)
explorer = ExplorerAgent(ai)
matcher = MatcherAgent(ai)
coach = CoachAgent(ai)
learner = LearnerAgent(ai)
jobs = AdzunaJobSource()

st.title("🧬 Loopbaan-Agent")
st.caption(
    "Ik begrijp welke loopbaanstap jij wilt zetten — ook als die niet uit een "
    "functietitel is af te leiden."
)

with st.expander("Hoe de app werkt"):
    st.markdown(
        """
1. **Profiler** maakt één compact Loopbaan-DNA.
2. **Explorer** vertaalt dit naar werkvelden, opgaven en zoekrichtingen.
3. **Scout** haalt vacatures op via Adzuna.
4. **Matcher** beoordeelt de feitelijke opdracht en overdraagbaarheid.
5. **Coach** helpt bij positionering en sollicitatiekeuze.
6. **Learner** verwerkt jouw feedback.
        """
    )

with st.expander("🔐 Privacy"):
    st.write(
        "Profiel- en vacatureteksten worden voor analyse naar de ingestelde "
        "AI-provider gestuurd. Verwijder gevoelige gegevens die niet nodig zijn."
    )

tab_profile, tab_explore, tab_jobs, tab_learning = st.tabs(
    ["1. Loopbaan-DNA", "2. Werkvelden", "3. Vacatures", "4. Leren"]
)

with tab_profile:
    st.subheader("Profiel en gewenste beweging")

    uploads = st.file_uploader(
        "Upload cv, profielschets of andere relevante documenten",
        type=["pdf", "docx", "txt"],
        accept_multiple_files=True,
    )

    if uploads:
        try:
            st.session_state.profile_text = read_uploaded_files(uploads)
            st.success(f"{len(uploads)} bestand(en) ingelezen.")
        except Exception as exc:
            st.error(f"Bestand kon niet worden gelezen: {exc}")

    st.session_state.profile_text = st.text_area(
        "Samengevoegde profieltekst",
        value=st.session_state.profile_text,
        height=260,
    )

    st.session_state.career_move = st.text_area(
        "Welke beweging wil je maken?",
        value=st.session_state.career_move,
        height=120,
        help=(
            "Beschrijf de gewenste verandering in inhoud, context, "
            "verantwoordelijkheid en betekenis. Niet alleen een functietitel."
        ),
    )

    profile_key = make_profile_hash(
        st.session_state.profile_text,
        st.session_state.career_move,
    )

    cached_dna = db.get_career_dna(profile_key)
    if cached_dna and st.session_state.career_dna is None:
        st.session_state.career_dna = cached_dna

    col1, col2 = st.columns([2, 1])

    with col1:
        if st.button(
            "🧬 Maak of vernieuw Loopbaan-DNA",
            type="primary",
            disabled=not st.session_state.profile_text.strip(),
        ):
            try:
                with st.spinner("Profiler analyseert de broninformatie..."):
                    dna = profiler.run(
                        st.session_state.profile_text,
                        st.session_state.career_move,
                    )
                    db.save_career_dna(
                        profile_key,
                        st.session_state.profile_text,
                        st.session_state.career_move,
                        dna,
                    )
                    st.session_state.career_dna = dna
                    st.session_state.exploration = None
                    st.session_state.results = []
                st.success("Loopbaan-DNA opgeslagen.")
                st.rerun()
            except Exception as exc:
                st.error(f"Profiler kon het Loopbaan-DNA niet maken: {exc}")

    with col2:
        if st.button("Gebruik opgeslagen DNA", disabled=cached_dna is None):
            st.session_state.career_dna = cached_dna
            st.rerun()

    if st.session_state.career_dna:
        dna = st.session_state.career_dna
        st.success("Loopbaan-DNA beschikbaar")
        st.markdown(f"### Professionele kern\n{dna.get('samenvatting', '')}")

        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("**Drijfveren**")
            for item in dna.get("identiteit", {}).get("drijfveren", []):
                st.write(f"• {item}")
            st.markdown("**Waarden**")
            for item in dna.get("identiteit", {}).get("waarden", []):
                st.write(f"• {item}")

        with c2:
            st.markdown("**Overdraagbare competenties**")
            for item in dna.get("overdraagbaar_vermogen", {}).get("competenties", []):
                st.write(f"• {item}")
            st.markdown("**Passende opgaven**")
            for item in dna.get("context", {}).get("passende_opgaven", []):
                st.write(f"• {item}")

        with c3:
            st.markdown("**Meer van**")
            for item in dna.get("ambitie", {}).get("meer_van", []):
                st.write(f"• {item}")
            st.markdown("**Minder van**")
            for item in dna.get("ambitie", {}).get("minder_van", []):
                st.write(f"• {item}")

        with st.expander("Volledig Loopbaan-DNA"):
            st.json(dna)

with tab_explore:
    if not st.session_state.career_dna:
        st.info("Maak eerst een Loopbaan-DNA.")
    else:
        profile_key = make_profile_hash(
            st.session_state.profile_text,
            st.session_state.career_move,
        )

        cached_exploration = db.get_exploration(profile_key)
        if cached_exploration and st.session_state.exploration is None:
            st.session_state.exploration = cached_exploration

        if st.button("🗺️ Verken werkvelden en onverwachte richtingen", type="primary"):
            try:
                with st.spinner("Explorer verbreedt de zoekruimte..."):
                    feedback = db.get_feedback(profile_key)
                    exploration = explorer.run(
                        st.session_state.career_dna,
                        feedback,
                    )
                    db.save_exploration(profile_key, exploration)
                    st.session_state.exploration = exploration
                st.success("Werkvelden en zoekclusters zijn uitgewerkt.")
                st.rerun()
            except Exception as exc:
                st.error(f"Explorer kon de zoekruimte niet maken: {exc}")

        if st.session_state.exploration:
            exploration = st.session_state.exploration

            st.markdown("### Werkvelden")
            for field in exploration.get("werkvelden", []):
                with st.container(border=True):
                    st.markdown(f"**{field.get('naam', '')}**")
                    st.write(field.get("waarom_passend", ""))
                    if field.get("typen_opgaven"):
                        st.caption("Opgaven: " + ", ".join(field["typen_opgaven"]))
                    if field.get("spanningsveld"):
                        st.warning(field["spanningsveld"])

            st.markdown("### Onverwachte richtingen")
            for direction in exploration.get("onverwachte_richtingen", []):
                with st.expander(direction.get("richting", "Richting")):
                    st.write(direction.get("brugredenering", ""))
                    st.write(
                        "**Nog te bewijzen:** "
                        + direction.get("wat_nog_bewezen_moet_worden", "")
                    )

            with st.expander("Zoekclusters"):
                st.json(exploration.get("zoekclusters", []))

with tab_jobs:
    if not st.session_state.career_dna or not st.session_state.exploration:
        st.info("Maak eerst het Loopbaan-DNA en laat Explorer werkvelden ontwikkelen.")
    else:
        a, b, c = st.columns(3)
        with a:
            st.session_state.location = st.text_input(
                "Locatie", value=st.session_state.location
            )
        with b:
            st.session_state.radius = st.number_input(
                "Straal (km)",
                min_value=5,
                max_value=200,
                value=int(st.session_state.radius),
                step=5,
            )
        with c:
            st.session_state.minimum_score = st.number_input(
                "Minimumscore",
                min_value=0,
                max_value=100,
                value=int(st.session_state.minimum_score),
                step=5,
            )

        d, e, f = st.columns(3)
        with d:
            st.session_state.jobs_per_term = st.number_input(
                "Vacatures per zoekterm",
                min_value=5,
                max_value=30,
                value=int(st.session_state.jobs_per_term),
                step=5,
            )
        with e:
            st.session_state.max_search_terms = st.number_input(
                "Maximaal zoektermen",
                min_value=3,
                max_value=20,
                value=int(st.session_state.max_search_terms),
                step=1,
            )
        with f:
            st.session_state.max_ai_matches = st.number_input(
                "Maximaal AI-beoordelingen",
                min_value=5,
                max_value=50,
                value=int(st.session_state.max_ai_matches),
                step=5,
                help="Begrenst tijd en kosten.",
            )

        if st.button("🔎 Zoek vanuit werkvelden", type="primary"):
            profile_key = make_profile_hash(
                st.session_state.profile_text,
                st.session_state.career_move,
            )
            feedback = db.get_feedback(profile_key)

            search_terms = []
            content_signals = []
            for cluster in st.session_state.exploration.get("zoekclusters", []):
                search_terms.extend(cluster.get("zoektermen", []))
                content_signals.extend(cluster.get("inhoudelijke_signalen", []))

            search_terms = unique_preserve_order(search_terms)[
                : int(st.session_state.max_search_terms)
            ]
            content_signals = unique_preserve_order(content_signals)

            raw_jobs = []
            errors = []
            progress = st.progress(0, text="Scout haalt vacatures op...")

            for index, term in enumerate(search_terms):
                progress.progress(
                    index / max(len(search_terms), 1),
                    text=f"Scout zoekt op: {term}",
                )
                try:
                    raw_jobs.extend(
                        jobs.search(
                            term=term,
                            location=st.session_state.location,
                            radius=int(st.session_state.radius),
                            results_per_term=int(st.session_state.jobs_per_term),
                        )
                    )
                except Exception as exc:
                    errors.append(f"{term}: {exc}")

            unique_jobs = {}
            for job in raw_jobs:
                key = jobs.job_key(job)
                if not key:
                    continue
                job["_local_score"] = jobs.local_score(job, content_signals)
                unique_jobs[key] = job

            candidates = sorted(
                unique_jobs.values(),
                key=lambda item: item.get("_local_score", 0),
                reverse=True,
            )[: int(st.session_state.max_ai_matches)]

            results = []
            overview = []

            for index, job in enumerate(candidates):
                title = job.get("title", "")
                progress.progress(
                    index / max(len(candidates), 1),
                    text=f"Matcher beoordeelt: {title[:55]}",
                )

                job_id = jobs.job_id(job)
                job_hash = jobs.job_hash(job)

                try:
                    cached_match = db.get_match(profile_key, job_id, job_hash)
                    from_cache = cached_match is not None

                    if cached_match is None:
                        match = matcher.run(
                            st.session_state.career_dna,
                            job,
                            feedback,
                        )
                        db.save_match(profile_key, job_id, job_hash, match)
                    else:
                        match = cached_match

                    overview.append(
                        {
                            "title": title,
                            "score": match.get("totaalscore"),
                            "classification": match.get("classificatie"),
                            "cache": from_cache,
                        }
                    )

                    if (
                        match.get("totaalscore") is not None
                        and match["totaalscore"] >= st.session_state.minimum_score
                    ):
                        results.append(
                            {
                                "job": job,
                                "match": match,
                                "coach": None,
                                "profile_key": profile_key,
                            }
                        )
                except Exception as exc:
                    overview.append(
                        {"title": title, "score": None, "error": str(exc)}
                    )

            progress.progress(1.0, text="Klaar")
            results.sort(
                key=lambda item: -(item["match"].get("totaalscore") or 0)
            )
            st.session_state.results = results
            st.session_state.match_overview = overview

            if errors:
                st.warning(
                    "Enkele zoekopdrachten mislukten:\n\n"
                    + "\n".join(f"- {error}" for error in errors)
                )

            st.success(
                f"{len(candidates)} vacatures beoordeeld; "
                f"{len(results)} matches boven de drempel."
            )

        if st.session_state.match_overview:
            with st.expander("Alle beoordelingen"):
                for item in sorted(
                    st.session_state.match_overview,
                    key=lambda x: (
                        x.get("score") is None,
                        -(x.get("score") or 0),
                    ),
                ):
                    if item.get("error"):
                        st.write(f"⚠️ {item['title']} — {item['error']}")
                    else:
                        cache = " · cache" if item.get("cache") else ""
                        st.write(
                            f"{item.get('score')} — {item['title']} · "
                            f"{item.get('classification')}{cache}"
                        )

        for index, result in enumerate(st.session_state.results):
            job = result["job"]
            match = result["match"]
            score = match.get("totaalscore") or 0
            colour = "🟢" if score >= 75 else "🟡" if score >= 60 else "🟠"

            with st.container(border=True):
                st.markdown(f"### {colour} {score} — {job.get('title', '')}")
                st.caption(
                    f"{job.get('company', {}).get('display_name', '')} · "
                    f"{job.get('location', {}).get('display_name', '')} · "
                    f"{match.get('classificatie', '')}"
                )

                if match.get("titel_is_misleidend"):
                    st.info(
                        "De titel is minder passend dan de feitelijke opdracht. "
                        "Dit is een verborgen match."
                    )

                scores = match.get("scores", {})
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Opdracht", scores.get("opdrachtmatch"))
                m2.metric("Bewijs", scores.get("bewijsuit_ervaring"))
                m3.metric("Overdracht", scores.get("overdraagbaarheid"))
                m4.metric("Context", scores.get("contextmatch"))

                st.write(match.get("korte_conclusie", ""))
                st.markdown("**Brugredenering**")
                st.write(match.get("brugredenering", ""))

                if match.get("sterke_bewijsregels"):
                    st.markdown("**Sterk bewijs uit ervaring**")
                    for item in match["sterke_bewijsregels"]:
                        st.write(f"• {item}")

                if match.get("risicos"):
                    st.markdown("**Risico's / te controleren**")
                    for item in match["risicos"]:
                        st.write(f"• {item}")

                if job.get("redirect_url"):
                    st.markdown(
                        f'<a href="{job["redirect_url"]}" target="_blank" '
                        f'rel="noopener noreferrer">Bekijk vacature ↗</a>',
                        unsafe_allow_html=True,
                    )

                if st.button(
                    "💬 Laat Coach deze match uitleggen",
                    key=f"coach_{index}",
                ):
                    try:
                        with st.spinner("Coach maakt een positioneringsadvies..."):
                            result["coach"] = coach.run(
                                st.session_state.career_dna,
                                job,
                                match,
                            )
                            st.session_state.results[index] = result
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Coach kon geen advies maken: {exc}")

                if result.get("coach"):
                    coach_result = result["coach"]
                    st.success(
                        coach_result.get("waarom_verrassend_passend", "")
                    )
                    st.markdown("**Positioneringszin**")
                    st.write(f"“{coach_result.get('positioneringszin', '')}”")
                    st.markdown("**Advies**")
                    st.write(
                        f"{coach_result.get('sollicitatieadvies', '')}: "
                        f"{coach_result.get('reden_advies', '')}"
                    )

                with st.expander("Geef feedback"):
                    judgement = st.radio(
                        "Oordeel",
                        ["goede match", "geen goede match"],
                        horizontal=True,
                        key=f"judgement_{index}",
                    )
                    reason = st.selectbox(
                        "Reden",
                        [
                            "opdracht past",
                            "overdraagbaarheid overtuigt",
                            "maatschappelijke context",
                            "verrassende brugrol",
                            "te specialistisch",
                            "te veel personeelsverantwoordelijkheid",
                            "te weinig senioriteit",
                            "voorwaarden",
                            "locatie",
                            "anders",
                        ],
                        key=f"reason_{index}",
                    )
                    note = st.text_input(
                        "Toelichting",
                        key=f"note_{index}",
                    )

                    if st.button("Feedback opslaan", key=f"feedback_{index}"):
                        db.save_feedback(
                            profile_key=result["profile_key"],
                            job_id=jobs.job_id(job),
                            title=job.get("title", ""),
                            organisation=job.get("company", {}).get(
                                "display_name",
                                "",
                            ),
                            judgement=judgement,
                            reason=reason,
                            note=note,
                        )
                        st.success("Feedback opgeslagen.")

with tab_learning:
    if not st.session_state.career_dna:
        st.info("Maak eerst een Loopbaan-DNA.")
    else:
        profile_key = make_profile_hash(
            st.session_state.profile_text,
            st.session_state.career_move,
        )
        feedback = db.get_feedback(profile_key)

        st.subheader(f"Opgeslagen feedback ({len(feedback)})")

        for item in feedback:
            st.write(
                f"• **{item['judgement']}** — {item.get('title')} bij "
                f"{item.get('organisation')} · {item.get('reason') or ''}"
            )

        if feedback and st.button("🧠 Laat Learner voorkeuren afleiden"):
            try:
                with st.spinner("Learner analyseert feedbackpatronen..."):
                    st.session_state.learning_profile = learner.run(
                        st.session_state.career_dna,
                        feedback,
                    )
                st.rerun()
            except Exception as exc:
                st.error(f"Learner kon feedback niet analyseren: {exc}")

        if st.session_state.learning_profile:
            st.json(st.session_state.learning_profile)

        if feedback and st.button("Feedback voor dit profiel wissen"):
            db.delete_feedback(profile_key)
            st.session_state.learning_profile = None
            st.success("Feedback gewist.")
            st.rerun()
