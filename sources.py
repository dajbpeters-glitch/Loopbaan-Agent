import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape

import requests
import streamlit as st
from bs4 import BeautifulSoup

from domain import clean_text, normalize_vacancy


def secret(name, default=None):
    try:
        return st.secrets[name]
    except Exception:
        return default


class Adzuna:
    name = "Adzuna"

    def available(self):
        return bool(secret("ADZUNA_APP_ID") and secret("ADZUNA_APP_KEY"))

    def search(self, term, location, radius, count):
        response = requests.get(
            "https://api.adzuna.com/v1/api/jobs/nl/search/1",
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
    source_map = {
        "Adzuna": Adzuna(),
        "Jooble": Jooble(),
    }
    return source_map[source_name].search(term, location, radius, count)


class SourceManager:
    def __init__(self):
        self.sources = [Adzuna(), Jooble()]

    def available(self):
        return [source for source in self.sources if source.available()]

    def search(self, terms, location, radius, count, enabled):
        """Zoek parallel per bron én zoekterm, met cache en diagnostiek."""
        vacancies = []
        diagnostics = {
            source.name: {"gevonden": 0, "fouten": []}
            for source in self.available()
            if source.name in enabled
        }

        tasks = [
            (source.name, term)
            for source in self.available()
            if source.name in enabled
            for term in terms
        ]

        if not tasks:
            return vacancies, diagnostics

        with ThreadPoolExecutor(max_workers=min(4, len(tasks))) as executor:
            future_map = {
                executor.submit(
                    cached_source_search,
                    source_name,
                    term,
                    location,
                    radius,
                    count,
                ): (source_name, term)
                for source_name, term in tasks
            }

            for future in as_completed(future_map):
                source_name, term = future_map[future]
                try:
                    items = future.result()
                    vacancies.extend(items)
                    diagnostics[source_name]["gevonden"] += len(items)
                except Exception as exc:
                    diagnostics[source_name]["fouten"].append(
                        f"{term}: {exc}"
                    )

        return vacancies, diagnostics


class JobPostingImporter:
    def import_url(self, url):
        response = requests.get(
            url,
            timeout=25,
            headers={
                "User-Agent": "Mozilla/5.0 Loopbaan-Agent/3.0.1"
            },
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
                "Geen JobPosting-gegevens gevonden. Upload of plak de "
                "vacaturetekst."
            )

        organisation = posting.get("hiringOrganization") or {}
        location = posting.get("jobLocation") or {}
        if isinstance(location, list):
            location = location[0] if location else {}
        address = location.get("address", {}) if isinstance(location, dict) else {}
        description = clean_text(
            BeautifulSoup(
                unescape(posting.get("description", "")),
                "html.parser",
            ).get_text("\n")
        )

        return normalize_vacancy(
            {
                "id": "url:"
                + hashlib.sha256(url.encode()).hexdigest()[:16],
                "title": posting.get("title", ""),
                "organisation": organisation.get("name", ""),
                "location": ", ".join(
                    str(address.get(field))
                    for field in [
                        "addressLocality",
                        "addressRegion",
                        "addressCountry",
                    ]
                    if address.get(field)
                ),
                "description": description,
                "url": url,
                "source": "Vacaturelink",
                "date_posted": posting.get("datePosted", ""),
                "valid_through": posting.get("validThrough", ""),
            }
        )
