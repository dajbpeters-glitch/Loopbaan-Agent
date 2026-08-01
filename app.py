import streamlit as st

from core import (
    Adzuna,
    AIClient,
    Coach,
    Database,
    Explorer,
    Matcher,
    Profiler,
    batches,
    cached_adzuna_search,
    profile_hash,
    read_uploaded_files,
    summarize_feedback,
    unique,
)


st.set_page_config(
    page_title="Loopbaan-Agent Lite 2.0",
    page_icon="🧭",
    layout="wide",
)

DEFAULTS = {
    "profile_text": "",
    "career_move": (
        "Ik zoek een volgende stap waarin mijn brede ervaring betekenisvol "
        "kan worden ingezet. De werkelijke opdracht en maatschappelijke opgave "
        "zijn belangrijker dan een bekende functietitel."
    ),
    "dna": None,
    "exploration": None,
    "results": [],
    "overview": [],
    "location": "Boxtel",
    "radius": 40,
    "jobs_per_term": 10,
    "max_terms": 10,
    "max_matches": 25,
    "minimum_score": 55,
}

for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value

db = Database()
db.initialize()

ai = AIClient()
profiler = Profiler(ai)
explorer = Explorer(ai)
matcher = Matcher(ai)
coach = Coach(ai)
adzuna = Adzuna()

st.title("🧭 Loopbaan-Agent Lite 2.0")
st.caption(
    "Vind de volgende loopbaanstap op basis van opdracht, overdraagbare "
    "ervaring en maatschappelijke context — niet alleen op functietitel."
)

tab1, tab2, tab3, tab4 = st.tabs(
    ["1. Loopbaan-DNA", "2. Werkvelden", "3. Vacatures", "4. Feedback"]
)

with tab1:
    uploads = st.file_uploader(
        "Upload cv en/of profielschets",
        type=["pdf", "docx", "txt"],
        accept_multiple_files=True,
    )

    if uploads:
        try:
            st.session_state.profile_text = read_uploaded_files(uploads)
            st.success(f"{len(uploads)} bestand(en) lokaal uitgelezen.")
        except Exception as exc:
            st.error(f"Bestand kon niet worden gelezen: {exc}")

    st.session_state.profile_text = st.text_area(
        "Profieltekst",
        value=st.session_state.profile_text,
        height=260,
    )

    st.session_state.career_move = st.text_area(
        "Welke beweging wil je maken?",
        value=st.session_state.career_move,
        height=120,
    )

    key = profile_hash(
        st.session_state.profile_text,
        st.session_state.career_move,
    )

    cached_dna = db.get_json("career_dna", key)
    if cached_dna and st.session_state.dna is None:
        st.session_state.dna = cached_dna

    if st.button(
        "🧬 Maak of vernieuw Loopbaan-DNA",
        type="primary",
        disabled=not st.session_state.profile_text.strip(),
    ):
        try:
            with st.spinner("Profiler maakt een compact Loopbaan-DNA..."):
                dna = profiler.run(
                    st.session_state.profile_text,
                    st.session_state.career_move,
                )
                db.save_json("career_dna", key, dna)
                st.session_state.dna = dna
                st.session_state.exploration = None
                st.session_state.results = []
            st.success("Loopbaan-DNA opgeslagen.")
            st.rerun()
        except Exception as exc:
            st.error(f"Profiler kon het Loopbaan-DNA niet maken: {exc}")

    if st.session_state.dna:
        dna = st.session_state.dna
        st.subheader("Professionele kern")
        st.write(dna.get("samenvatting", ""))

        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown("**Drijfveren en waarden**")
            for item in dna.get("drijfveren", []) + dna.get("waarden", []):
                st.write(f"• {item}")

        with col2:
            st.markdown("**Overdraagbare competenties**")
            for item in dna.get("overdraagbare_competenties", []):
                st.write(f"• {item}")

        with col3:
            st.markdown("**Gewenste beweging**")
            for item in dna.get("gewenste_beweging", []):
                st.write(f"• {item}")

        with st.expander("Volledig Loopbaan-DNA"):
            st.json(dna)


with tab2:
    if not st.session_state.dna:
        st.info("Maak eerst een Loopbaan-DNA.")
    else:
        key = profile_hash(
            st.session_state.profile_text,
            st.session_state.career_move,
        )
        cached_exploration = db.get_json("explorations", key)

        if cached_exploration and st.session_state.exploration is None:
            st.session_state.exploration = cached_exploration

        if st.button("🗺️ Verken werkvelden", type="primary"):
            try:
                feedback = db.get_feedback(key)
                summary = summarize_feedback(feedback)

                with st.spinner("Explorer verbreedt de zoekruimte..."):
                    result = explorer.run(st.session_state.dna, summary)
                    db.save_json("explorations", key, result)
                    st.session_state.exploration = result

                st.success("Werkvelden en zoekclusters opgeslagen.")
                st.rerun()
            except Exception as exc:
                st.error(f"Explorer kon de werkvelden niet maken: {exc}")

        if st.session_state.exploration:
            for field in st.session_state.exploration.get("werkvelden", []):
                with st.container(border=True):
                    st.markdown(f"### {field.get('naam', '')}")
                    st.write(field.get("waarom_passend", ""))
                    st.caption(
                        "Opgaven: " + ", ".join(field.get("typen_opgaven", []))
                    )
                    if field.get("spanningsveld"):
                        st.warning(field["spanningsveld"])

            st.subheader("Onverwachte richtingen")
            for direction in st.session_state.exploration.get(
                "onverwachte_richtingen",
                [],
            ):
                with st.expander(direction.get("richting", "Richting")):
                    st.write(direction.get("brugredenering", ""))
                    st.write(
                        "**Nog te bewijzen:** "
                        + direction.get("wat_nog_bewezen_moet_worden", "")
                    )


with tab3:
    if not st.session_state.dna or not st.session_state.exploration:
        st.info("Maak eerst het Loopbaan-DNA en de werkvelden.")
    else:
        c1, c2, c3 = st.columns(3)
        with c1:
            st.session_state.location = st.text_input(
                "Locatie",
                value=st.session_state.location,
            )
        with c2:
            st.session_state.radius = st.number_input(
                "Straal (km)",
                min_value=5,
                max_value=200,
                value=int(st.session_state.radius),
                step=5,
            )
        with c3:
            st.session_state.minimum_score = st.number_input(
                "Minimumscore",
                min_value=0,
                max_value=100,
                value=int(st.session_state.minimum_score),
                step=5,
            )

        c4, c5, c6 = st.columns(3)
        with c4:
            st.session_state.jobs_per_term = st.number_input(
                "Vacatures per zoekterm",
                min_value=5,
                max_value=25,
                value=int(st.session_state.jobs_per_term),
                step=5,
            )
        with c5:
            st.session_state.max_terms = st.number_input(
                "Maximaal zoektermen",
                min_value=3,
                max_value=15,
                value=int(st.session_state.max_terms),
                step=1,
            )
        with c6:
            st.session_state.max_matches = st.number_input(
                "Maximaal AI-beoordelingen",
                min_value=5,
                max_value=50,
                value=int(st.session_state.max_matches),
                step=5,
            )

        if st.button("🔎 Zoek en beoordeel", type="primary"):
            key = profile_hash(
                st.session_state.profile_text,
                st.session_state.career_move,
            )

            feedback = db.get_feedback(key)
            feedback_summary = summarize_feedback(feedback)

            terms = []
            signals = []
            for cluster in st.session_state.exploration.get("zoekclusters", []):
                terms.extend(cluster.get("zoektermen", []))
                signals.extend(cluster.get("inhoudelijke_signalen", []))

            terms = unique(terms)[: int(st.session_state.max_terms)]
            signals = unique(signals)
            negatives = feedback_summary.get("negatieve_voorkeuren", [])

            raw_jobs = []
            source_errors = []

            for term in terms:
                try:
                    raw_jobs.extend(
                        cached_adzuna_search(
                            term,
                            st.session_state.location,
                            int(st.session_state.radius),
                            int(st.session_state.jobs_per_term),
                        )
                    )
                except Exception as exc:
                    source_errors.append(f"{term}: {exc}")

            unique_jobs = {}
            for raw_job in raw_jobs:
                job = adzuna.prepare(raw_job)
                unique_jobs[job["_id"]] = job

            candidates = sorted(
                unique_jobs.values(),
                key=lambda job: adzuna.local_score(job, signals, negatives),
                reverse=True,
            )[: int(st.session_state.max_matches)]

            results = []
            overview = []
            progress = st.progress(0, text="Vacatures beoordelen...")

            uncached = []
            cached_results = {}

            for job in candidates:
                job_hash = adzuna.job_hash(job)
                saved = db.get_match(key, job_hash)
                if saved:
                    cached_results[job["_id"]] = saved
                else:
                    uncached.append(job)

            total_batches = max(1, (len(uncached) + 4) // 5)

            for batch_index, job_batch in enumerate(batches(uncached, 5)):
                progress.progress(
                    batch_index / total_batches,
                    text=f"Matcher beoordeelt batch {batch_index + 1}...",
                )

                try:
                    batch_matches = matcher.run_batch(
                        st.session_state.dna,
                        feedback_summary,
                        job_batch,
                    )

                    by_id = {item["id"]: item for item in batch_matches}

                    for job in job_batch:
                        match = by_id.get(job["_id"])
                        if not match:
                            continue

                        db.save_match(key, adzuna.job_hash(job), match)
                        cached_results[job["_id"]] = match

                except Exception as exc:
                    for job in job_batch:
                        overview.append(
                            {
                                "title": job.get("title", ""),
                                "error": str(exc),
                            }
                        )

            for job in candidates:
                match = cached_results.get(job["_id"])
                if not match:
                    continue

                score = match.get("totaalscore")
                overview.append(
                    {
                        "title": job.get("title", ""),
                        "score": score,
                        "classification": match.get("classificatie", ""),
                    }
                )

                if score is not None and score >= st.session_state.minimum_score:
                    results.append(
                        {
                            "job": job,
                            "match": match,
                            "coach": None,
                            "profile_key": key,
                        }
                    )

            results.sort(
                key=lambda item: -(item["match"].get("totaalscore") or 0)
            )
            st.session_state.results = results
            st.session_state.overview = overview
            progress.progress(1.0, text="Klaar")

            if source_errors:
                st.warning(
                    "Niet alle zoektermen konden worden opgehaald:\n\n"
                    + "\n".join(f"- {item}" for item in source_errors)
                )

            st.success(
                f"{len(candidates)} vacatures geselecteerd; "
                f"{len(results)} matches boven de drempel."
            )

        if st.session_state.overview:
            with st.expander("Alle beoordelingen"):
                for item in sorted(
                    st.session_state.overview,
                    key=lambda row: (
                        row.get("score") is None,
                        -(row.get("score") or 0),
                    ),
                ):
                    if item.get("error"):
                        st.write(f"⚠️ {item['title']} — {item['error']}")
                    else:
                        st.write(
                            f"{item.get('score')} — {item['title']} · "
                            f"{item.get('classification', '')}"
                        )

        for index, result in enumerate(st.session_state.results):
            job = result["job"]
            match = result["match"]
            score = match.get("totaalscore") or 0
            icon = "🟢" if score >= 75 else "🟡" if score >= 60 else "🟠"

            with st.container(border=True):
                st.markdown(f"### {icon} {score} — {job.get('title', '')}")
                st.caption(
                    f"{job.get('company', {}).get('display_name', '')} · "
                    f"{job.get('location', {}).get('display_name', '')} · "
                    f"{match.get('classificatie', '')}"
                )

                if match.get("titel_is_misleidend"):
                    st.info(
                        "De feitelijke opdracht past beter dan de functietitel "
                        "doet vermoeden."
                    )

                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Opdracht", match.get("opdrachtmatch"))
                m2.metric("Bewijs", match.get("bewijsuit_ervaring"))
                m3.metric("Overdracht", match.get("overdraagbaarheid"))
                m4.metric("Context", match.get("contextmatch"))

                st.write(match.get("belangrijkste_argument", ""))
                st.markdown("**Brugredenering**")
                st.write(match.get("brugredenering", ""))
                st.warning(match.get("belangrijkste_risico", ""))

                if job.get("redirect_url"):
                    st.markdown(
                        f'<a href="{job["redirect_url"]}" target="_blank" '
                        f'rel="noopener noreferrer">Bekijk vacature ↗</a>',
                        unsafe_allow_html=True,
                    )

                if st.button("💬 Coachadvies", key=f"coach_{index}"):
                    try:
                        with st.spinner("Coach maakt advies..."):
                            result["coach"] = coach.run(
                                st.session_state.dna,
                                job,
                                match,
                            )
                            st.session_state.results[index] = result
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Coach kon geen advies maken: {exc}")

                if result.get("coach"):
                    st.success(result["coach"])

                with st.expander("Geef feedback"):
                    judgement = st.radio(
                        "Oordeel",
                        ["goede match", "geen goede match"],
                        horizontal=True,
                        key=f"judgement_{index}",
                    )
                    reason = st.selectbox(
                        "Belangrijkste reden",
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

                    if st.button("Feedback opslaan", key=f"save_{index}"):
                        db.add_feedback(
                            profile_key=result["profile_key"],
                            job_id=job["_id"],
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


with tab4:
    key = profile_hash(
        st.session_state.profile_text,
        st.session_state.career_move,
    )
    feedback = db.get_feedback(key)
    summary = summarize_feedback(feedback)

    st.subheader(f"Opgeslagen beoordelingen: {len(feedback)}")
    st.json(summary)

    for item in feedback:
        st.write(
            f"• **{item['judgement']}** — {item.get('title')} bij "
            f"{item.get('organisation')} · {item.get('reason')}"
        )
