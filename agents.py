import json


class ProfilerAgent:
    def __init__(self, ai):
        self.ai = ai

    def run(self, profile_text: str, career_move: str) -> dict:
        system_prompt = """
Je bent de Profiler-agent van Loopbaan-Agent.
Je maakt een compact en herbruikbaar Loopbaan-DNA. Je maakt geen functietitel
tot identiteit en zoekt nadrukkelijk naar overdraagbaarheid.
"""
        user_prompt = f"""
BRONPROFIEL:
{profile_text[:45000]}

GEWENSTE LOOPBAANBEWEGING:
{career_move}

Geef uitsluitend geldig JSON:
{{
  "identiteit": {{
    "professionele_kern": "...",
    "drijfveren": ["..."],
    "waarden": ["..."]
  }},
  "ervaring": {{
    "domeinen": ["..."],
    "verantwoordelijkheden": ["..."],
    "aantoonbare_resultaten": ["..."],
    "senioriteitsniveau": "..."
  }},
  "overdraagbaar_vermogen": {{
    "competenties": ["..."],
    "patronen_die_breed_inzetbaar_zijn": ["..."],
    "bewijsregels": ["..."]
  }},
  "werkstijl": {{
    "leiderschap": ["..."],
    "samenwerking": ["..."],
    "besluitvorming": ["..."],
    "voorkeursomgeving": ["..."]
  }},
  "ambitie": {{
    "gewenste_beweging": ["..."],
    "meer_van": ["..."],
    "minder_van": ["..."],
    "harde_grenzen": ["..."]
  }},
  "context": {{
    "passende_opgaven": ["..."],
    "passende_organisaties": ["..."],
    "doelgroepen": ["..."]
  }},
  "aannames_en_leemtes": ["..."],
  "samenvatting": "maximaal 180 woorden"
}}
"""
        return self.ai.ask_json(system_prompt, user_prompt, 1800)


class ExplorerAgent:
    def __init__(self, ai):
        self.ai = ai

    def run(self, career_dna: dict, feedback: list[dict]) -> dict:
        system_prompt = """
Je bent de Explorer-agent van Loopbaan-Agent.
Je denkt eerst in werkvelden, maatschappelijke opgaven, typen opdrachten en
organisatorische contexten. Functietitels zijn slechts praktische zoektermen.
"""
        feedback_text = "\n".join(
            f"- {item['judgement']}: {item.get('title')} – "
            f"{item.get('reason') or ''} {item.get('note') or ''}"
            for item in feedback
        ) or "Nog geen feedback."

        user_prompt = f"""
LOOPBAAN-DNA:
{json.dumps(career_dna, ensure_ascii=False)}

GEBRUIKERSFEEDBACK:
{feedback_text}

Geef uitsluitend geldig JSON:
{{
  "werkvelden": [
    {{
      "naam": "...",
      "waarom_passend": "...",
      "typen_opgaven": ["..."],
      "mogelijke_organisaties": ["..."],
      "spanningsveld": "..."
    }}
  ],
  "onverwachte_richtingen": [
    {{
      "richting": "...",
      "brugredenering": "...",
      "wat_nog_bewezen_moet_worden": "..."
    }}
  ],
  "zoekclusters": [
    {{
      "cluster": "...",
      "zoektermen": ["maximaal 6 concrete termen"],
      "inhoudelijke_signalen": ["woorden of thema's in vacatureteksten"]
    }}
  ],
  "vermijd_zoekvernauwing": ["..."],
  "prioriteiten": ["maximaal 5 meest kansrijke richtingen"]
}}
"""
        return self.ai.ask_json(system_prompt, user_prompt, 1800)


class MatcherAgent:
    WEIGHTS = {
        "opdrachtmatch": 0.25,
        "bewijsuit_ervaring": 0.15,
        "overdraagbaarheid": 0.20,
        "contextmatch": 0.12,
        "waarden_en_werkstijl": 0.10,
        "voorwaarden_en_risico": 0.10,
        "ontwikkelpotentieel": 0.08,
    }

    def __init__(self, ai):
        self.ai = ai

    @staticmethod
    def _clamp(value):
        try:
            return max(0, min(100, round(float(value))))
        except (TypeError, ValueError):
            return None

    def run(self, career_dna: dict, job: dict, feedback: list[dict]) -> dict:
        system_prompt = """
Je bent de Matcher-agent van Loopbaan-Agent.
De functietitel is slechts een label. Je beoordeelt de echte opdracht,
overdraagbaarheid, bewijs, context, risico's en ontwikkelpotentieel.
"""
        feedback_text = "\n".join(
            f"- {item['judgement']}: {item.get('title')} – "
            f"{item.get('reason') or ''}"
            for item in feedback
        ) or "Nog geen feedback."

        user_prompt = f"""
LOOPBAAN-DNA:
{json.dumps(career_dna, ensure_ascii=False)}

GEBRUIKERSFEEDBACK:
{feedback_text}

VACATURE:
Titel: {job.get('title', '')}
Organisatie: {job.get('company', {}).get('display_name', '')}
Omschrijving:
{job.get('description', '')[:12000]}

Gebruik scores van 0-100. Classificeer als:
"logische stap", "brugrol", "verrassende match" of "onvoldoende match".

Geef uitsluitend geldig JSON:
{{
  "scores": {{
    "opdrachtmatch": 0,
    "bewijsuit_ervaring": 0,
    "overdraagbaarheid": 0,
    "contextmatch": 0,
    "waarden_en_werkstijl": 0,
    "voorwaarden_en_risico": 0,
    "ontwikkelpotentieel": 0
  }},
  "classificatie": "...",
  "titel_is_misleidend": false,
  "sterke_bewijsregels": ["..."],
  "brugredenering": "...",
  "risicos": ["..."],
  "te_controleren": ["..."],
  "korte_conclusie": "maximaal 3 zinnen"
}}
"""
        result = self.ai.ask_json(system_prompt, user_prompt, 1300)
        raw_scores = result.get("scores", {})
        scores = {
            name: self._clamp(raw_scores.get(name))
            for name in self.WEIGHTS
        }
        result["scores"] = scores

        if all(value is not None for value in scores.values()):
            result["totaalscore"] = round(
                sum(scores[name] * weight for name, weight in self.WEIGHTS.items())
            )
        else:
            result["totaalscore"] = None

        return result


class CoachAgent:
    def __init__(self, ai):
        self.ai = ai

    def run(self, career_dna: dict, job: dict, match: dict) -> dict:
        system_prompt = """
Je bent de Coach-agent van Loopbaan-Agent.
Je vertaalt een inhoudelijke match naar een eerlijke en overtuigende uitleg.
Je overdrijft niet.
"""
        user_prompt = f"""
LOOPBAAN-DNA:
{json.dumps(career_dna, ensure_ascii=False)}

VACATURE:
Titel: {job.get('title', '')}
Organisatie: {job.get('company', {}).get('display_name', '')}
Omschrijving: {job.get('description', '')[:9000]}

MATCHER-UITKOMST:
{json.dumps(match, ensure_ascii=False)}

Geef uitsluitend geldig JSON:
{{
  "waarom_verrassend_passend": "...",
  "positioneringszin": "...",
  "drie_gesprekspunten": ["..."],
  "kritische_vragen_aan_werkgever": ["..."],
  "ontwikkelverhaal": "...",
  "sollicitatieadvies": "wel solliciteren / eerst bellen / niet prioriteren",
  "reden_advies": "..."
}}
"""
        return self.ai.ask_json(system_prompt, user_prompt, 1100)


class LearnerAgent:
    def __init__(self, ai):
        self.ai = ai

    def run(self, career_dna: dict, feedback: list[dict]) -> dict:
        system_prompt = """
Je bent de Learner-agent van Loopbaan-Agent.
Je leidt voorzichtig voorkeurspatronen af uit expliciete feedback. Je wijzigt
nooit feiten uit het Loopbaan-DNA.
"""
        user_prompt = f"""
BESTAAND LOOPBAAN-DNA:
{json.dumps(career_dna, ensure_ascii=False)}

FEEDBACK:
{json.dumps(feedback, ensure_ascii=False)}

Geef uitsluitend geldig JSON:
{{
  "geleerde_voorkeuren": ["..."],
  "waarschijnlijke_afkeer": ["..."],
  "nieuwe_hypotheses": ["..."],
  "niet_genoeg_bewijs_voor": ["..."],
  "advies_aan_explorer": ["..."],
  "advies_aan_matcher": ["..."]
}}
"""
        return self.ai.ask_json(system_prompt, user_prompt, 900)
