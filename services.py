import hashlib
import json
import re
import sqlite3
from datetime import datetime

import anthropic
import requests
import streamlit as st
from docx import Document
from pypdf import PdfReader


def make_profile_hash(profile_text: str, career_move: str) -> str:
    source = f"{profile_text}\n---\n{career_move}"
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def normalize(text: str) -> str:
    return " ".join((text or "").lower().split())


def unique_preserve_order(values: list[str]) -> list[str]:
    return list(dict.fromkeys(
        value.strip()
        for value in values
        if isinstance(value, str) and value.strip()
    ))


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


def read_uploaded_files(files) -> str:
    return "\n\n--- DOCUMENT ---\n\n".join(read_file(file) for file in files)


class AIClient:
    def __init__(self) -> None:
        self.client = anthropic.Anthropic(
            api_key=self._secret("ANTHROPIC_API_KEY"),
            timeout=60.0,
            max_retries=2,
        )
        self.model = self._secret(
            "ANTHROPIC_MODEL",
            "claude-haiku-4-5-20251001",
        )

    @staticmethod
    def _secret(name: str, default: str | None = None) -> str:
        try:
            return st.secrets[name]
        except Exception:
            if default is not None:
                return default
            raise KeyError(f"Ontbrekende Streamlit secret: {name}")

    def ask_json(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
    ) -> dict:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=0,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )

        if not response.content:
            raise ValueError("De AI gaf geen inhoud terug.")

        return self._extract_json(response.content[0].text)

    @staticmethod
    def _extract_json(text: str) -> dict:
        text = (text or "").strip()

        if not text:
            raise ValueError("De AI gaf een leeg antwoord terug.")

        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, flags=re.DOTALL)
            if not match:
                raise ValueError(
                    "De AI gaf geen geldig JSON-object terug. "
                    f"Eerste deel: {text[:250]}"
                )
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    "Het gevonden JSON-object kon niet worden gelezen. "
                    f"Eerste deel: {match.group(0)[:250]}"
                ) from exc


class Database:
    def __init__(self, path: str) -> None:
        self.path = path

    def connect(self):
        return sqlite3.connect(self.path)

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS career_dna (
                    profile_key TEXT PRIMARY KEY,
                    source_profile TEXT NOT NULL,
                    career_move TEXT NOT NULL,
                    dna_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS explorations (
                    profile_key TEXT PRIMARY KEY,
                    exploration_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS matches (
                    profile_key TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    job_hash TEXT NOT NULL,
                    match_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (profile_key, job_id, job_hash)
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
            conn.commit()

    def save_career_dna(
        self,
        profile_key: str,
        source_profile: str,
        career_move: str,
        dna: dict,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO career_dna
                (profile_key, source_profile, career_move, dna_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    profile_key,
                    source_profile,
                    career_move,
                    json.dumps(dna, ensure_ascii=False),
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
            conn.commit()

    def get_career_dna(self, profile_key: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT dna_json FROM career_dna WHERE profile_key = ?",
                (profile_key,),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def save_exploration(self, profile_key: str, exploration: dict) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO explorations
                (profile_key, exploration_json, created_at)
                VALUES (?, ?, ?)
                """,
                (
                    profile_key,
                    json.dumps(exploration, ensure_ascii=False),
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
            conn.commit()

    def get_exploration(self, profile_key: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT exploration_json FROM explorations WHERE profile_key = ?",
                (profile_key,),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def save_match(
        self,
        profile_key: str,
        job_id: str,
        job_hash: str,
        match: dict,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO matches
                (profile_key, job_id, job_hash, match_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    profile_key,
                    job_id,
                    job_hash,
                    json.dumps(match, ensure_ascii=False),
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
            conn.commit()

    def get_match(
        self,
        profile_key: str,
        job_id: str,
        job_hash: str,
    ) -> dict | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT match_json
                FROM matches
                WHERE profile_key = ? AND job_id = ? AND job_hash = ?
                """,
                (profile_key, job_id, job_hash),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def save_feedback(
        self,
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
            conn.commit()

    def get_feedback(self, profile_key: str, limit: int = 20) -> list[dict]:
        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT job_id, title, organisation, judgement, reason, note
                FROM feedback
                WHERE profile_key = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (profile_key, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_feedback(self, profile_key: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "DELETE FROM feedback WHERE profile_key = ?",
                (profile_key,),
            )
            conn.commit()


class AdzunaJobSource:
    URL = "https://api.adzuna.com/v1/api/jobs/nl/search/1"

    @staticmethod
    def _secret(name: str) -> str:
        try:
            return st.secrets[name]
        except Exception as exc:
            raise KeyError(f"Ontbrekende Streamlit secret: {name}") from exc

    def search(
        self,
        term: str,
        location: str,
        radius: int,
        results_per_term: int,
    ) -> list[dict]:
        response = requests.get(
            self.URL,
            params={
                "app_id": self._secret("ADZUNA_APP_ID"),
                "app_key": self._secret("ADZUNA_APP_KEY"),
                "what": term,
                "where": location,
                "distance": radius,
                "results_per_page": results_per_term,
                "content-type": "application/json",
            },
            timeout=25,
        )
        response.raise_for_status()
        return response.json().get("results", [])

    @staticmethod
    def job_key(job: dict) -> str:
        return str(job.get("id") or normalize(
            f"{job.get('title', '')}|"
            f"{job.get('company', {}).get('display_name', '')}"
        ))

    @staticmethod
    def job_id(job: dict) -> str:
        return str(job.get("id") or AdzunaJobSource.job_key(job))

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
    def local_score(job: dict, signals: list[str]) -> int:
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
                score += 2
        return score
