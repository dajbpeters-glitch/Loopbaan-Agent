import hashlib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape
from urllib.parse import urlsplit, urlunsplit

import requests
import streamlit as st
from bs4 import BeautifulSoup

from domain import clean_text, normalize_vacancy


def secret(name, default=None):
    try:
        return st.secrets[name]
    except Exception:
        return default


def safe_error(exc):
    """Maak een foutmelding geschikt voor de interface zonder secrets of URL-query."""
    status = getattr(getattr(exc, "response", None), "status_code", None)

    if status == 429:
        return "Tijdelijk begrensd door de bron. Probeer later opnieuw."
    if status in {500, 502, 503, 504}:
        return "Bron tijdelijk niet beschikbaar."
    if status in {401, 403}:
        return "Toegang geweigerd. Controleer de API-sleutel."
    if isinstance(exc, requests.Timeout):
        return "Bron reageerde niet binnen de wachttijd."
    if isinstance(exc, requests.ConnectionError):
        return "Verbinding met de bron is mislukt."

    message = str(exc)
    # Verwijder URLs, querystrings en bekende secretwaarden.
    message = re.sub(r"https?://\S+", "[URL verborgen]", message)
    for name in ["ADZUNA_APP_ID", "ADZUNA_APP_KEY", "JOOBLE_API_KEY"]:
        value = secret(name)
        if value:
            message = message.replace(str(value), "[verborgen]")
    return message[:180] or "Onbekende bronfout."


class SourceSearchStopped(Exception):
    """Interne melding dat een bron voor deze zoekactie moet stoppen."""


class Adzuna:
    name = "Adzuna"
    url = "https://api.adzuna.com/v1/api/jobs/nl/search/1"

    def available(self):
        return bool(secret("ADZUNA_APP_ID") and secret("ADZUNA_APP_KEY"))

    def search(self, term, location, radius, count):
        response = requests.get(
            self.url,
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

        results = []
        for job in response.json().get("results", []):
            results.append(
                normalize_vacancy(
                    {
                        "id": f"adzuna:{job.get('id', '')}",
                        "title": job.get("title", ""),
                        "organisation": job.get("company", {}).get(
                            "display_name", ""
                        ),
                        "location": job.get("location", {}).get(
                            "display_name", ""
                        ),
                        "description": job.get("description", ""),
                        "url": job.get("redirect_url", ""),
                        "source": self.name,
                        "date_posted": job.get("created", ""),
                    }
                )
            )
        return results


class Jooble:
    name = "Jooble"

    def available(self):
        return bool(secret("JOOBLE_API_KEY"))

    @staticmethod
    def nearest_radius(radius):
        allowed = [0, 4, 8, 16, 26, 40, 80]
        return min(allowed, key=lambda value: abs(value - radius))

    def search(self, term, location, radius, count):
        response = requests.post(
            f"https://jooble.org/api/{secret('JOOBLE_API_KEY')}",
            json={
                "keywords": term,
                "location": location,
                "radius": str(self.nearest_radius(radius)),
                "page": "1",
                "ResultOnPage": str(count),
                "companysearch": "false",
            },
            timeout=25,
        )
        response.raise_for_status()

        results = []
        for job in response.json().get("jobs", []):
            results.append(
                normalize_vacancy(
                    {
                        "id": f"jooble:{job.get('id', '')}",
                        "title": job.get("title", ""),
                        "organisation": job.get("company", ""),
                        "location": job.get("location", ""),
                        "description": job.get("snippet", ""),
                        "url": job.get("link", ""),
                        "source": self.name,
                        "source_detail": job.get("source", ""),
                        "salary": job.get("salary", ""),
                        "date_posted": job.get("updated", ""),
                    }
                )
            )
        return results


@st.cache_data(ttl="6h", max_entries=500, show_spinner=False)
def cached_source_search(source_name, term, location, radius, count):
    source_map = {"Adzuna": Adzuna(), "Jooble": Jooble()}
    return source_map[source_name].search(term, location, radius, count)


class SourceManager:
    ADZUNA_MAX_TERMS = 5
    ADZUNA_INTERVAL_SECONDS = 2.6

    def __init__(self):
        self.sources = [Adzuna(), Jooble()]

    def available(self):
        return [source for source in self.sources if source.available()]

    def _search_adzuna(self, terms, location, radius, count):
        """Adzuna bewust sequentieel en begrensd om 429 te voorkomen."""
        jobs = []
        errors = []
        used_terms = terms[: self.ADZUNA_MAX_TERMS]
        status = "gereed"

        for index, term in enumerate(used_terms):
            if index:
                time.sleep(self.ADZUNA_INTERVAL_SECONDS)

            try:
                items = cached_source_search(
                    "Adzuna", term, location, radius, count
                )
                jobs.extend(items)
            except requests.HTTPError as exc:
                code = getattr(exc.response, "status_code", None)
                if code == 429:
                    errors.append(safe_error(exc))
                    status = "begrensd"
                    break
                if code in {500, 502, 503, 504}:
                    # Eén gecontroleerde retry na korte rust.
                    time.sleep(3)
                    try:
                        items = cached_source_search(
                            "Adzuna", term, location, radius, count
                        )
                        jobs.extend(items)
                        continue
                    except Exception as retry_exc:
                        errors.append(safe_error(retry_exc))
                        status = "tijdelijk niet beschikbaar"
                        continue
                errors.append(safe_error(exc))
                status = "fout"
            except Exception as exc:
                errors.append(safe_error(exc))
                status = "fout"

        return jobs, {
            "gevonden": len(jobs),
            "status": status,
            "zoektermen_gebruikt": len(used_terms),
            "fouten": list(dict.fromkeys(errors)),
        }

    def _search_jooble(self, terms, location, radius, count):
        """Jooble mag beperkt parallel zoeken en blijft onafhankelijk werken."""
        jobs = []
        errors = []

        with ThreadPoolExecutor(max_workers=min(3, max(1, len(terms)))) as executor:
            future_map = {
                executor.submit(
                    cached_source_search,
                    "Jooble",
                    term,
                    location,
                    radius,
                    count,
                ): term
                for term in terms
            }

            for future in as_completed(future_map):
                try:
                    jobs.extend(future.result())
                except Exception as exc:
                    errors.append(safe_error(exc))

        return jobs, {
            "gevonden": len(jobs),
            "status": "gereed" if not errors else "gedeeltelijk gelukt",
            "zoektermen_gebruikt": len(terms),
            "fouten": list(dict.fromkeys(errors)),
        }

    def search(self, terms, location, radius, count, enabled):
        """Zoek bronnen onafhankelijk; uitval van één bron blokkeert de rest niet."""
        jobs = []
        diagnostics = {}
        tasks = {}

        with ThreadPoolExecutor(max_workers=2) as executor:
            if "Adzuna" in enabled and Adzuna().available():
                tasks[
                    executor.submit(
                        self._search_adzuna,
                        terms,
                        location,
                        radius,
                        count,
                    )
                ] = "Adzuna"

            if "Jooble" in enabled and Jooble().available():
                tasks[
                    executor.submit(
                        self._search_jooble,
                        terms,
                        location,
                        radius,
                        count,
                    )
                ] = "Jooble"

            for future in as_completed(tasks):
                source_name = tasks[future]
                try:
                    source_jobs, source_diagnostics = future.result()
                    jobs.extend(source_jobs)
                    diagnostics[source_name] = source_diagnostics
                except Exception as exc:
                    diagnostics[source_name] = {
                        "gevonden": 0,
                        "status": "fout",
                        "zoektermen_gebruikt": 0,
                        "fouten": [safe_error(exc)],
                    }

        return jobs, diagnostics


class JobPostingImporter:
    def import_url(self, url):
        response = requests.get(
            url,
            timeout=25,
            headers={"User-Agent": "Mozilla/5.0 Loopbaan-Agent/3.0.2"},
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        posting = None

        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or script.get_text() or "")
            except Exception:
                continue

            queue = data if isinstance(data, list) else [data]
            for candidate in queue:
                if (
                    isinstance(candidate, dict)
                    and candidate.get("@type") == "JobPosting"
                ):
                    posting = candidate
                    break

                graph = (
                    candidate.get("@graph", [])
                    if isinstance(candidate, dict)
                    else []
                )
                for item in graph:
                    if (
                        isinstance(item, dict)
                        and item.get("@type") == "JobPosting"
                    ):
                        posting = item
                        break
                if posting:
                    break
            if posting:
                break

        if not posting:
            raise ValueError(
                "Geen JobPosting-gegevens gevonden. Plak de vacaturetekst "
                "of upload een PDF/DOCX."
            )

        organisation = posting.get("hiringOrganization") or {}
        location = self._location(posting.get("jobLocation"))

        return normalize_vacancy(
            {
                "id": "url:"
                + hashlib.sha256(url.encode("utf-8")).hexdigest()[:16],
                "title": posting.get("title", ""),
                "organisation": organisation.get("name", ""),
                "location": location,
                "description": self._html_to_text(
                    posting.get("description", "")
                ),
                "url": url,
                "source": "Vacaturelink",
                "date_posted": posting.get("datePosted", ""),
                "valid_through": posting.get("validThrough", ""),
            }
        )

    @staticmethod
    def _html_to_text(value):
        soup = BeautifulSoup(unescape(value or ""), "html.parser")
        return clean_text(soup.get_text("\n"))

    @staticmethod
    def _location(value):
        if isinstance(value, list):
            value = value[0] if value else {}
        if not isinstance(value, dict):
            return ""
        address = value.get("address") or {}
        if not isinstance(address, dict):
            return ""
        parts = [
            address.get("addressLocality"),
            address.get("addressRegion"),
            address.get("addressCountry"),
        ]
        return ", ".join(str(part) for part in parts if part)
