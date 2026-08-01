from concurrent.futures import ThreadPoolExecutor, as_completed

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
    read_single_uploaded_file,
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
    "manual_job_text": "",
    "manual_job_title": "",
    "manual_job_org": "",
    "manual_job_result": None,
    "location": "Boxtel",
    "radius": 40,
    "jobs_per_term": 10,
    "max_terms": 10,
    "max_matches": 15,
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


st.markdown(
    """
    <style>
    @media (max-width: 768px) {
        div[data-testid="stHorizontalBlock"] {
            flex-direction: column;
        }
        div[data-testid="column"] {
            width: 100% !important;
            flex: 1 1 100% !important;
        }
        .block-container {
            padding-left: 1rem;
            padding-right: 1rem;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
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
            items = dna.get("drijfveren", []) + dna.get("waarden", [])
            if items:
                st.markdown("\n".join(f"- {item}" for item in items))
            else:
                st.caption("Nog niet ingevuld")

        with col2:
            st.markdown("**Overdraagbare competenties**")
            items = dna.get("overdraagbare_competenties", [])
            if items:
                st.markdown("\n".join(f"- {item}" for item in items))
            else:
                st.caption("Nog niet ingevuld")

        with col3:
            st.markdown("**Gewenste beweging**")
            items = dna.get("gewenste_beweging", [])
            if items:
                st.markdown("\n".join(f"- {item}" for item in items))
            else:
                st.caption("Nog niet ingevuld")

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

            st.subheader("Roltypen en zoekrichtingen")
            for role in st.session_state.exploration.get("roltypen", []):
                with st.container(border=True):
                    st.markdown(
                        f"**{role.get('naam', '')}** · {role.get('type', '')}"
                    )
                    st.write(role.get("waarom_passend", ""))
                    if role.get("zoektermen"):
                        st.caption(
                            "Zoektermen: " + ", ".join(role.get("zoektermen", []))
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
                max_value=40,
                value=int(st.session_state.max_matches),
                step=5,
                help=(
                    "15 is een goede balans tussen snelheid en dekking. "
                    "Eerdere matches worden uit de cache geladen."
                ),
            )

        st.caption(
            "De Matcher beoordeelt maximaal vijf vacatures per batch en "
            "verwerkt twee batches tegelijk. Een tweede zoekactie is meestal "
            "sneller doordat eerdere beoordelingen worden hergebruikt."
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

            # Eerst gebalanceerd uit roltypen halen.
            role_terms = {}
            for role in st.session_state.exploration.get("roltypen", []):
                role_type = role.get("type", "anders")
                role_terms.setdefault(role_type, [])
                role_terms[role_type].extend(role.get("zoektermen", []))

            preferred_order = [
                "leidinggevend",
                "adviserend",
                "regisserend",
                "programmatisch",
                "netwerkgericht",
                "veranderkundig",
                "bedrijfsvoering",
                "anders",
            ]

            # Rondes langs de typen voorkomen dat één categorie alles domineert.
            max_rounds = 3
            for round_index in range(max_rounds):
                for role_type in preferred_order:
                    values = unique(role_terms.get(role_type, []))
                    if round_index < len(values):
                        terms.append(values[round_index])

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
            duplicate_count = 0

            for raw_job in raw_jobs:
                job = adzuna.prepare(raw_job)
                duplicate_key = adzuna.duplicate_key(job)

                if duplicate_key in unique_jobs:
                    duplicate_count += 1

                    # Bewaar bij dubbelen de versie met de langste omschrijving.
                    existing = unique_jobs[duplicate_key]
                    if len(job.get("description", "")) > len(
                        existing.get("description", "")
                    ):
                        unique_jobs[duplicate_key] = job
                else:
                    unique_jobs[duplicate_key] = job

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

            job_batches = list(batches(uncached, 5))
            total_batches = max(1, len(job_batches))

            # Streamlit session_state is alleen veilig in de hoofdthread.
            # Leg benodigde waarden daarom vooraf lokaal vast.
            dna_for_matching = st.session_state.dna
            feedback_for_matching = feedback_summary

            def assess_batch(job_batch):
                # Een eigen client per worker voorkomt gedeelde clientstatus.
                local_matcher = Matcher(AIClient())
                return job_batch, local_matcher.run_batch(
                    dna_for_matching,
                    feedback_for_matching,
                    job_batch,
                )

            completed_batches = 0

            # Twee parallelle batches geven duidelijke snelheidswinst zonder
            # onnodig veel druk op de API of rate limits.
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(assess_batch, job_batch)
                    for job_batch in job_batches
                ]

                for future in as_completed(futures):
                    completed_batches += 1
                    progress.progress(
                        completed_batches / total_batches,
                        text=(
                            f"Matcher heeft "
                            f"{min(completed_batches * 5, len(uncached))} van "
                            f"{len(uncached)} vacatures beoordeeld..."
                        ),
                    )

                    try:
                        job_batch, batch_matches = future.result()
                        by_id = {item["id"]: item for item in batch_matches}

                        for job in job_batch:
                            match = by_id.get(job["_id"])
                            if not match:
                                continue

                            db.save_match(key, adzuna.job_hash(job), match)
                            cached_results[job["_id"]] = match

                    except Exception as exc:
                        # Koppel de fout zo goed mogelijk aan de batch.
                        failed_batch = []
                        try:
                            failed_batch = future.result()[0]
                        except Exception:
                            pass

                        if failed_batch:
                            for job in failed_batch:
                                overview.append(
                                    {
                                        "title": job.get("title", ""),
                                        "error": str(exc),
                                    }
                                )
                        else:
                            overview.append(
                                {
                                    "title": "Vacaturebatch",
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

                if score is not None:
                    if score >= st.session_state.minimum_score:
                        group = "sterke_match"
                    elif score >= max(40, st.session_state.minimum_score - 15):
                        group = "mogelijk_interessant"
                    else:
                        group = "lager_beoordeeld"

                    results.append(
                        {
                            "job": job,
                            "match": match,
                            "coach": None,
                            "profile_key": key,
                            "group": group,
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

            strong_count = sum(
                1 for item in results if item.get("group") == "sterke_match"
            )
            possible_count = sum(
                1 for item in results
                if item.get("group") == "mogelijk_interessant"
            )

            st.success(
                f"{len(candidates)} unieke vacatures beoordeeld; "
                f"{duplicate_count} dubbele resultaten verwijderd; "
                f"{strong_count} sterke matches en "
                f"{possible_count} mogelijk interessante vacatures."
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

        def render_result_card(index, result):
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

                risk = match.get("belangrijkste_risico", "")
                if risk:
                    st.warning(risk)

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

        strong = [
            (i, item)
            for i, item in enumerate(st.session_state.results)
            if item.get("group") == "sterke_match"
        ]
        possible = [
            (i, item)
            for i, item in enumerate(st.session_state.results)
            if item.get("group") == "mogelijk_interessant"
        ]
        lower = [
            (i, item)
            for i, item in enumerate(st.session_state.results)
            if item.get("group") == "lager_beoordeeld"
        ]

        st.subheader(f"Sterke matches ({len(strong)})")
        if not strong:
            st.caption("Geen vacatures boven de ingestelde minimumscore.")
        for index, result in strong:
            render_result_card(index, result)

        with st.expander(f"Mogelijk interessant ({len(possible)})", expanded=True):
            for index, result in possible:
                render_result_card(index, result)

        with st.expander(f"Lager beoordeeld ({len(lower)})"):
            for index, result in lower:
                render_result_card(index, result)


        st.divider()
        st.subheader("Vacature handmatig toevoegen")
        st.caption(
            "Gebruik dit wanneer een vacature niet via Adzuna wordt gevonden. "
            "Plak de tekst of upload een PDF, DOCX of TXT-bestand."
        )

        manual_upload = st.file_uploader(
            "Upload vacaturebestand",
            type=["pdf", "docx", "txt"],
            key="manual_job_upload",
        )

        if manual_upload:
            try:
                st.session_state.manual_job_text = read_single_uploaded_file(
                    manual_upload
                )
                st.success("Vacaturebestand ingelezen.")
            except Exception as exc:
                st.error(f"Vacaturebestand kon niet worden gelezen: {exc}")

        st.session_state.manual_job_title = st.text_input(
            "Functietitel",
            value=st.session_state.manual_job_title,
            key="manual_title_input",
        )
        st.session_state.manual_job_org = st.text_input(
            "Organisatie",
            value=st.session_state.manual_job_org,
            key="manual_org_input",
        )
        st.session_state.manual_job_text = st.text_area(
            "Vacaturetekst",
            value=st.session_state.manual_job_text,
            height=220,
            key="manual_text_input",
        )

        if st.button(
            "🧪 Beoordeel handmatig toegevoegde vacature",
            disabled=not st.session_state.manual_job_text.strip(),
        ):
            key = profile_hash(
                st.session_state.profile_text,
                st.session_state.career_move,
            )
            feedback_summary = summarize_feedback(db.get_feedback(key))

            manual_job = adzuna.prepare(
                {
                    "title": st.session_state.manual_job_title or "Handmatige vacature",
                    "company": {
                        "display_name": st.session_state.manual_job_org
                        or "Onbekende organisatie"
                    },
                    "location": {"display_name": ""},
                    "description": st.session_state.manual_job_text,
                    "redirect_url": "",
                }
            )

            try:
                with st.spinner("Matcher beoordeelt de vacature..."):
                    match_list = matcher.run_batch(
                        st.session_state.dna,
                        feedback_summary,
                        [manual_job],
                    )
                    if not match_list:
                        raise ValueError("Matcher gaf geen beoordeling terug.")

                    st.session_state.manual_job_result = {
                        "job": manual_job,
                        "match": match_list[0],
                    }
                st.success("Vacature beoordeeld.")
            except Exception as exc:
                st.error(f"Handmatige beoordeling mislukte: {exc}")

        if st.session_state.manual_job_result:
            manual = st.session_state.manual_job_result
            match = manual["match"]
            job = manual["job"]

            with st.container(border=True):
                st.markdown(
                    f"### Handmatige beoordeling: "
                    f"{match.get('totaalscore')} — {job.get('title', '')}"
                )
                st.caption(
                    f"{job.get('company', {}).get('display_name', '')} · "
                    f"{match.get('classificatie', '')}"
                )
                st.write(match.get("belangrijkste_argument", ""))
                st.markdown("**Brugredenering**")
                st.write(match.get("brugredenering", ""))
                if match.get("belangrijkste_risico"):
                    st.warning(match.get("belangrijkste_risico"))


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
