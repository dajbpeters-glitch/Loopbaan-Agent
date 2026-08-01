import hashlib
import json
import re
import sqlite3
from datetime import datetime
from typing import Any

import anthropic
import requests
import streamlit as st
from docx import Document
from pypdf import PdfReader


# ============================================================
# Algemene helpers
# ============================================================

def secret(name: str, default: str | None = None) -> str:
    try:
        return st.secrets[name]
    except Exception:
        if default is not None:
            return default
        raise KeyError(f"Ontbrekende Streamlit secret: {name}")


def profile_hash(profile_text: str, career_move: str) -> str:
    source = f"{profile_text}\n---\n{career_move}"
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def normalize(text: str) -> str:
    return " ".join((text or "").lower().split())


def unique(values: list[str]) -> list[str]:
    return list(
        dict.fromkeys(
            value.strip()
            for value in values
            if isinstance(value, str) and value.strip()
        )
    )


def clamp_score(value: Any) -> int | None:
    try:
        return max(0, min(100, round(float(value))))
    except (TypeError, ValueError):
        return None


def ensure_string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def ensure_list(value: Any) -> list[str]:
    """
    Zet AI-uitvoer veilig om naar een lijst met strings.
    Voorkomt dat Streamlit letter voor letter door één string loopt.
    """
    if value is None:
        return []

    if isinstance(value, list):
        result = []
        for item in value:
            if item is None:
                continue
            if isinstance(item, str):
                cleaned = item.strip()
            else:
                cleaned = ensure_string(item).strip()
            if cleaned:
                result.append(cleaned)
        return result

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []

        # Splits alleen wanneer de tekst duidelijk meerdere items bevat.
        parts = re.split(r"\n+|;\s*|(?<=\.)\s+(?=[A-ZÀ-ÖØ-Þ])", text)
        parts = [part.strip(" •-\t") for part in parts if part.strip(" •-\t")]

        return parts if len(parts) > 1 else [text]

    return [ensure_string(value)]


def normalize_career_dna(data: dict) -> dict:
    normalized = dict(data or {})

    list_fields = [
        "drijfveren",
        "waarden",
        "ervaringsdomeinen",
        "aantoonbare_resultaten",
        "overdraagbare_competenties",
        "bewijsregels",
        "werkstijl",
        "gewenste_beweging",
        "meer_van",
        "minder_van",
        "harde_grenzen",
        "passende_opgaven",
        "passende_organisaties",
        "aannames_en_leemtes",
    ]

    for field in list_fields:
        normalized[field] = ensure_list(normalized.get(field))

    normalized["professionele_kern"] = ensure_string(
        normalized.get("professionele_kern")
    )
    normalized["samenvatting"] = ensure_string(normalized.get("samenvatting"))

    return normalized


def normalize_exploration(data: dict) -> dict:
    normalized = dict(data or {})

    workfields = []
    for item in normalized.get("werkvelden") or []:
        if not isinstance(item, dict):
            continue
        workfields.append(
            {
                "naam": ensure_string(item.get("naam")),
                "waarom_passend": ensure_string(item.get("waarom_passend")),
                "typen_opgaven": ensure_list(item.get("typen_opgaven")),
                "mogelijke_organisaties": ensure_list(
                    item.get("mogelijke_organisaties")
                ),
                "spanningsveld": ensure_string(item.get("spanningsveld")),
            }
        )

    directions = []
    for item in normalized.get("onverwachte_richtingen") or []:
        if not isinstance(item, dict):
            continue
        directions.append(
            {
                "richting": ensure_string(item.get("richting")),
                "brugredenering": ensure_string(item.get("brugredenering")),
                "wat_nog_bewezen_moet_worden": ensure_string(
                    item.get("wat_nog_bewezen_moet_worden")
                ),
            }
        )

    clusters = []
    for item in normalized.get("zoekclusters") or []:
        if not isinstance(item, dict):
            continue
        clusters.append(
            {
                "cluster": ensure_string(item.get("cluster")),
                "zoektermen": ensure_list(item.get("zoektermen")),
                "inhoudelijke_signalen": ensure_list(
                    item.get("inhoudelijke_signalen")
                ),
            }
        )

    normalized["werkvelden"] = workfields
    normalized["onverwachte_richtingen"] = directions
    normalized["zoekclusters"] = clusters
    normalized["prioriteiten"] = ensure_list(normalized.get("prioriteiten"))
    return normalized


def normalize_match_batch(data: dict) -> dict:
    normalized = {"matches": []}

    for item in (data or {}).get("matches") or []:
        if not isinstance(item, dict):
            continue

        normalized["matches"].append(
            {
                "id": ensure_string(item.get("id")),
                "totaalscore": clamp_score(item.get("totaalscore")),
                "classificatie": ensure_string(item.get("classificatie")),
                "titel_is_misleidend": bool(item.get("titel_is_misleidend")),
                "opdrachtmatch": clamp_score(item.get("opdrachtmatch")),
                "bewijsuit_ervaring": clamp_score(item.get("bewijsuit_ervaring")),
                "overdraagbaarheid": clamp_score(item.get("overdraagbaarheid")),
                "contextmatch": clamp_score(item.get("contextmatch")),
                "belangrijkste_argument": ensure_string(
                    item.get("belangrijkste_argument")
                ),
                "belangrijkste_risico": ensure_string(
                    item.get("belangrijkste_risico")
                ),
                "brugredenering": ensure_string(item.get("brugredenering")),
            }
        )

    return normalized


# ============================================================
# Documentverwerking — volledig lokaal
# ============================================================

def read_pdf(file) -> str:
    reader = PdfReader(file)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def read_docx(file) -> str:
    document = Document(file)
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def read_file(file) -> str:
    name = file.name.lower()
    if name.endswith(".pdf"):
        return read_pdf(file)
    if name.endswith(".docx"):
        return read_docx(file)
    return file.read().decode("utf-8", errors="ignore")


def clean_profile_text(text: str) -> str:
    text = text.replace("\x00", " ")
    lines = []
    seen = set()

    for raw_line in text.splitlines():
        line = " ".join(raw_line.split()).strip()
        if not line:
            continue

        key = line.lower()
        if key in seen:
            continue

        seen.add(key)
        lines.append(line)

    return "\n".join(lines)


def read_uploaded_files(files) -> str:
    parts = [read_file(file) for file in files]
    return clean_profile_text("\n\n--- DOCUMENT ---\n\n".join(parts))


# ============================================================
# Anthropic — verplichte gestructureerde tool-output
# ============================================================

class AIClient:
    def __init__(self) -> None:
        self.client = anthropic.Anthropic(
            api_key=secret("ANTHROPIC_API_KEY"),
            timeout=75.0,
            max_retries=2,
        )
        self.model = secret(
            "ANTHROPIC_MODEL",
            "claude-haiku-4-5-20251001",
        )

    def structured(
        self,
        *,
        tool_name: str,
        description: str,
        schema: dict,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 1800,
    ) -> dict:
        tools = [
            {
                "name": tool_name,
                "description": description,
                "input_schema": schema,
            }
        ]

        response = self._request_tool(
            tools=tools,
            tool_name=tool_name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=max_tokens,
        )

        if response.stop_reason == "max_tokens":
            response = self._request_tool(
                tools=tools,
                tool_name=tool_name,
                system_prompt=system_prompt,
                user_prompt=(
                    user_prompt
                    + "\n\nFormuleer compacter. Vul alle verplichte velden in "
                      "en voltooi de tool-aanroep volledig."
                ),
                max_tokens=min(max_tokens * 2, 4096),
            )

        for block in response.content:
            if getattr(block, "type", None) == "tool_use":
                if getattr(block, "name", None) == tool_name:
                    result = getattr(block, "input", None)
                    if isinstance(result, dict):
                        return result

        raise ValueError(
            f"Claude heeft de verplichte tool '{tool_name}' niet volledig ingevuld."
        )

    def text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 900,
    ) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=0,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )

        parts = [
            getattr(block, "text", "")
            for block in response.content
            if getattr(block, "type", None) == "text"
        ]
        result = "\n".join(parts).strip()

        if not result:
            raise ValueError("Claude gaf geen leesbare coachreactie terug.")

        return result

    def _request_tool(
        self,
        *,
        tools: list[dict],
        tool_name: str,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
    ):
        return self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=0,
            system=system_prompt,
            tools=tools,
            tool_choice={
                "type": "tool",
                "name": tool_name,
                "disable_parallel_tool_use": True,
            },
            messages=[{"role": "user", "content": user_prompt}],
        )


# ============================================================
# Schema's
# ============================================================

STRING_ARRAY = {
    "type": "array",
    "items": {"type": "string"},
}

CAREER_DNA_SCHEMA = {
    "type": "object",
    "properties": {
        "professionele_kern": {"type": "string"},
        "drijfveren": {**STRING_ARRAY, "maxItems": 6},
        "waarden": {**STRING_ARRAY, "maxItems": 6},
        "ervaringsdomeinen": {**STRING_ARRAY, "maxItems": 8},
        "aantoonbare_resultaten": {**STRING_ARRAY, "maxItems": 8},
        "overdraagbare_competenties": {**STRING_ARRAY, "maxItems": 10},
        "bewijsregels": {**STRING_ARRAY, "maxItems": 8},
        "werkstijl": {**STRING_ARRAY, "maxItems": 8},
        "gewenste_beweging": {**STRING_ARRAY, "maxItems": 6},
        "meer_van": {**STRING_ARRAY, "maxItems": 6},
        "minder_van": {**STRING_ARRAY, "maxItems": 6},
        "harde_grenzen": {**STRING_ARRAY, "maxItems": 6},
        "passende_opgaven": {**STRING_ARRAY, "maxItems": 8},
        "passende_organisaties": {**STRING_ARRAY, "maxItems": 8},
        "aannames_en_leemtes": {**STRING_ARRAY, "maxItems": 6},
        "samenvatting": {"type": "string"},
    },
    "required": [
        "professionele_kern",
        "drijfveren",
        "waarden",
        "ervaringsdomeinen",
        "aantoonbare_resultaten",
        "overdraagbare_competenties",
        "bewijsregels",
        "werkstijl",
        "gewenste_beweging",
        "meer_van",
        "minder_van",
        "harde_grenzen",
        "passende_opgaven",
        "passende_organisaties",
        "aannames_en_leemtes",
        "samenvatting",
    ],
}

EXPLORATION_SCHEMA = {
    "type": "object",
    "properties": {
        "werkvelden": {
            "type": "array",
            "maxItems": 8,
            "items": {
                "type": "object",
                "properties": {
                    "naam": {"type": "string"},
                    "waarom_passend": {"type": "string"},
                    "typen_opgaven": {**STRING_ARRAY, "maxItems": 5},
                    "mogelijke_organisaties": {**STRING_ARRAY, "maxItems": 5},
                    "spanningsveld": {"type": "string"},
                },
                "required": [
                    "naam",
                    "waarom_passend",
                    "typen_opgaven",
                    "mogelijke_organisaties",
                    "spanningsveld",
                ],
            },
        },
        "onverwachte_richtingen": {
            "type": "array",
            "maxItems": 6,
            "items": {
                "type": "object",
                "properties": {
                    "richting": {"type": "string"},
                    "brugredenering": {"type": "string"},
                    "wat_nog_bewezen_moet_worden": {"type": "string"},
                },
                "required": [
                    "richting",
                    "brugredenering",
                    "wat_nog_bewezen_moet_worden",
                ],
            },
        },
        "zoekclusters": {
            "type": "array",
            "maxItems": 6,
            "items": {
                "type": "object",
                "properties": {
                    "cluster": {"type": "string"},
                    "zoektermen": {**STRING_ARRAY, "maxItems": 6},
                    "inhoudelijke_signalen": {**STRING_ARRAY, "maxItems": 8},
                },
                "required": [
                    "cluster",
                    "zoektermen",
                    "inhoudelijke_signalen",
                ],
            },
        },
        "prioriteiten": {**STRING_ARRAY, "maxItems": 5},
    },
    "required": [
        "werkvelden",
        "onverwachte_richtingen",
        "zoekclusters",
        "prioriteiten",
    ],
}

MATCH_BATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "matches": {
            "type": "array",
            "maxItems": 5,
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "totaalscore": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 100,
                    },
                    "classificatie": {
                        "type": "string",
                        "enum": [
                            "logische stap",
                            "brugrol",
                            "verrassende match",
                            "onvoldoende match",
                        ],
                    },
                    "titel_is_misleidend": {"type": "boolean"},
                    "opdrachtmatch": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 100,
                    },
                    "bewijsuit_ervaring": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 100,
                    },
                    "overdraagbaarheid": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 100,
                    },
                    "contextmatch": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 100,
                    },
                    "belangrijkste_argument": {"type": "string"},
                    "belangrijkste_risico": {"type": "string"},
                    "brugredenering": {"type": "string"},
                },
                "required": [
                    "id",
                    "totaalscore",
                    "classificatie",
                    "titel_is_misleidend",
                    "opdrachtmatch",
                    "bewijsuit_ervaring",
                    "overdraagbaarheid",
                    "contextmatch",
                    "belangrijkste_argument",
                    "belangrijkste_risico",
                    "brugredenering",
                ],
            },
        }
    },
    "required": ["matches"],
}


# ============================================================
# Gespecialiseerde agents
# ============================================================

class Profiler:
    def __init__(self, ai: AIClient) -> None:
        self.ai = ai

    def run(self, profile_text: str, career_move: str) -> dict:
        result = self.ai.structured(
            tool_name="save_career_dna",
            description=(
                "Leg één compact, feitelijk en herbruikbaar Loopbaan-DNA vast. "
                "Gebruik de functietitel niet als identiteit. Verbind ervaring "
                "met overdraagbaarheid en de gewenste loopbaanbeweging."
            ),
            schema=CAREER_DNA_SCHEMA,
            system_prompt=(
                "Je bent een kritische loopbaananalist. Scheid aantoonbare "
                "ervaring, interpretaties en aannames. Formuleer compact."
            ),
            user_prompt=f"""
Analyseer het profiel en de gewenste beweging.

PROFIEL:
{profile_text[:50000]}

GEWENSTE BEWEGING:
{career_move}
""",
            max_tokens=2200,
        )
        return normalize_career_dna(result)


class Explorer:
    def __init__(self, ai: AIClient) -> None:
        self.ai = ai

    def run(self, dna: dict, feedback_summary: dict) -> dict:
        result = self.ai.structured(
            tool_name="save_exploration",
            description=(
                "Leg kansrijke werkvelden, maatschappelijke opgaven, "
                "onverwachte richtingen en praktische zoekclusters vast."
            ),
            schema=EXPLORATION_SCHEMA,
            system_prompt=(
                "Je bent een loopbaanverkenner. Denk eerst in werkvelden en "
                "opgaven. Gebruik functietitels alleen als praktische zoekterm."
            ),
            user_prompt=f"""
LOOPBAAN-DNA:
{json.dumps(dna, ensure_ascii=False)}

EXPLICIETE GEBRUIKERSVOORKEUREN:
{json.dumps(feedback_summary, ensure_ascii=False)}
""",
            max_tokens=2000,
        )
        return normalize_exploration(result)


class Matcher:
    def __init__(self, ai: AIClient) -> None:
        self.ai = ai

    def run_batch(
        self,
        dna: dict,
        feedback_summary: dict,
        jobs: list[dict],
    ) -> list[dict]:
        compact_jobs = [
            {
                "id": str(job["_id"]),
                "titel": job.get("title", ""),
                "organisatie": job.get("company", {}).get("display_name", ""),
                "locatie": job.get("location", {}).get("display_name", ""),
                "omschrijving": job.get("description", "")[:7000],
            }
            for job in jobs
        ]

        result = self.ai.structured(
            tool_name="save_match_batch",
            description=(
                "Beoordeel maximaal vijf vacatures ten opzichte van één "
                "Loopbaan-DNA. Beoordeel de feitelijke opdracht, niet alleen "
                "de functietitel."
            ),
            schema=MATCH_BATCH_SCHEMA,
            system_prompt=(
                "Je bent een kritische vacaturematcher. Vermijd wensdenken. "
                "Een hoge score vereist aantoonbare aansluiting én een "
                "geloofwaardige brugredenering."
            ),
            user_prompt=f"""
LOOPBAAN-DNA:
{json.dumps(dna, ensure_ascii=False)}

EXPLICIETE VOORKEUREN:
{json.dumps(feedback_summary, ensure_ascii=False)}

VACATURES:
{json.dumps(compact_jobs, ensure_ascii=False)}
""",
            max_tokens=1800,
        )
        return normalize_match_batch(result).get("matches", [])


class Coach:
    def __init__(self, ai: AIClient) -> None:
        self.ai = ai

    def run(self, dna: dict, job: dict, match: dict) -> str:
        return self.ai.text(
            system_prompt=(
                "Je bent een eerlijke loopbaancoach. Leg compact uit waarom "
                "de vacature wel of niet prioriteit verdient en hoe de kandidaat "
                "de overstap geloofwaardig kan positioneren."
            ),
            user_prompt=f"""
LOOPBAAN-DNA:
{json.dumps(dna, ensure_ascii=False)}

VACATURE:
Titel: {job.get('title', '')}
Organisatie: {job.get('company', {}).get('display_name', '')}
Omschrijving: {job.get('description', '')[:9000]}

MATCH:
{json.dumps(match, ensure_ascii=False)}

Geef:
1. waarom dit verrassend passend kan zijn;
2. één positioneringszin;
3. drie gesprekspunten;
4. twee kritische vragen;
5. advies: wel solliciteren, eerst bellen of niet prioriteren.
""",
            max_tokens=750,
        )


# ============================================================
# Feedback — eerst deterministisch, zonder AI-kosten
# ============================================================

POSITIVE_REASONS = {
    "opdracht past",
    "overdraagbaarheid overtuigt",
    "maatschappelijke context",
    "verrassende brugrol",
}

NEGATIVE_REASONS = {
    "te specialistisch",
    "te veel personeelsverantwoordelijkheid",
    "te weinig senioriteit",
    "voorwaarden",
    "locatie",
}


def summarize_feedback(feedback: list[dict]) -> dict:
    positive = []
    negative = []
    notes = []

    for item in feedback:
        reason = item.get("reason", "")
        judgement = item.get("judgement", "")
        note = item.get("note", "").strip()

        if judgement == "goede match" or reason in POSITIVE_REASONS:
            positive.append(reason)
        if judgement == "geen goede match" or reason in NEGATIVE_REASONS:
            negative.append(reason)
        if note:
            notes.append(note)

    return {
        "positieve_voorkeuren": unique(positive),
        "negatieve_voorkeuren": unique(negative),
        "toelichtingen": notes[-10:],
        "aantal_beoordelingen": len(feedback),
    }


# ============================================================
# Database
# ============================================================

class Database:
    def __init__(self, path: str = "loopbaan_agent.db") -> None:
        self.path = path

    def connect(self):
        return sqlite3.connect(self.path)

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS career_dna (
                    profile_key TEXT PRIMARY KEY,
                    data_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS explorations (
                    profile_key TEXT PRIMARY KEY,
                    data_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS matches (
                    profile_key TEXT NOT NULL,
                    job_hash TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (profile_key, job_hash)
                );

                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_key TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    title TEXT,
                    organisation TEXT,
                    judgement TEXT NOT NULL,
                    reason TEXT,
                    note TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )

    def save_json(self, table: str, key: str, data: dict) -> None:
        if table not in {"career_dna", "explorations"}:
            raise ValueError("Ongeldige tabel.")

        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {table}
                (profile_key, data_json, created_at)
                VALUES (?, ?, ?)
                """,
                (
                    key,
                    json.dumps(data, ensure_ascii=False),
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )

    def get_json(self, table: str, key: str) -> dict | None:
        if table not in {"career_dna", "explorations"}:
            raise ValueError("Ongeldige tabel.")

        with self.connect() as conn:
            row = conn.execute(
                f"SELECT data_json FROM {table} WHERE profile_key = ?",
                (key,),
            ).fetchone()

        if not row:
            return None

        data = json.loads(row[0])
        if table == "career_dna":
            return normalize_career_dna(data)
        return normalize_exploration(data)

    def save_match(self, profile_key: str, job_hash: str, data: dict) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO matches
                (profile_key, job_hash, data_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    profile_key,
                    job_hash,
                    json.dumps(data, ensure_ascii=False),
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )

    def get_match(self, profile_key: str, job_hash: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT data_json FROM matches
                WHERE profile_key = ? AND job_hash = ?
                """,
                (profile_key, job_hash),
            ).fetchone()

        return normalize_match_batch(
            {"matches": [json.loads(row[0])]}
        )["matches"][0] if row else None

    def add_feedback(
        self,
        *,
        profile_key: str,
        job_id: str,
        title: str,
        organisation: str,
        judgement: str,
        reason: str,
        note: str,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO feedback
                (profile_key, job_id, title, organisation,
                 judgement, reason, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile_key,
                    job_id,
                    title,
                    organisation,
                    judgement,
                    reason,
                    note,
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )

    def get_feedback(self, profile_key: str) -> list[dict]:
        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT title, organisation, judgement, reason, note
                FROM feedback
                WHERE profile_key = ?
                ORDER BY id DESC
                LIMIT 50
                """,
                (profile_key,),
            ).fetchall()

        return [dict(row) for row in rows]


# ============================================================
# Vacaturebron en lokale voorselectie
# ============================================================

class Adzuna:
    URL = "https://api.adzuna.com/v1/api/jobs/nl/search/1"

    def search(
        self,
        term: str,
        location: str,
        radius: int,
        count: int,
    ) -> list[dict]:
        response = requests.get(
            self.URL,
            params={
                "app_id": secret("ADZUNA_APP_ID"),
                "app_key": secret("ADZUNA_APP_KEY"),
                "what": term,
                "where": location,
                "distance": radius,
                "results_per_page": count,
                "content-type": "application/json",
            },
            timeout=25,
        )
        response.raise_for_status()
        return response.json().get("results", [])

    @staticmethod
    def prepare(job: dict) -> dict:
        result = dict(job)
        result["_id"] = str(
            job.get("id")
            or hashlib.sha256(
                (
                    job.get("title", "")
                    + job.get("company", {}).get("display_name", "")
                ).encode("utf-8")
            ).hexdigest()[:16]
        )
        return result

    @staticmethod
    def job_hash(job: dict) -> str:
        source = json.dumps(
            {
                "title": job.get("title"),
                "company": job.get("company", {}).get("display_name"),
                "description": job.get("description"),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(source.encode("utf-8")).hexdigest()

    @staticmethod
    def local_score(job: dict, signals: list[str], negatives: list[str]) -> int:
        text = normalize(
            " ".join(
                [
                    job.get("title", ""),
                    job.get("description", ""),
                    job.get("company", {}).get("display_name", ""),
                    job.get("category", {}).get("label", ""),
                ]
            )
        )

        score = 1 if job.get("description") else 0

        for signal in signals:
            if normalize(signal) in text:
                score += 3

        for negative in negatives:
            if normalize(negative) in text:
                score -= 3

        return score


@st.cache_data(ttl="6h", max_entries=200, show_spinner=False)
def cached_adzuna_search(
    term: str,
    location: str,
    radius: int,
    count: int,
) -> list[dict]:
    return Adzuna().search(term, location, radius, count)


def batches(items: list, size: int = 5):
    for index in range(0, len(items), size):
        yield items[index:index + size]
