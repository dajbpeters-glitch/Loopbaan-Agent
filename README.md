# Loopbaan-Agent 3.0.1

Multi-source update van 3.0.

## Verbeteringen

- Adzuna en Jooble zoeken parallel;
- caching per bron, zoekterm, locatie, straal en aantal resultaten;
- bron-onafhankelijk vacaturemodel;
- bronlabels bij iedere vacature;
- inhoudelijke ontdubbeling over bronnen heen;
- zoekdiagnostiek per bron;
- fout van één bron blokkeert de andere bron niet;
- persoonlijke vacaturebibliotheek en JobPosting-linkimport blijven beschikbaar.

## Bestanden

```text
app.py
ai_engine.py
domain.py
sources.py
storage.py
requirements.txt
README.md
```

## Streamlit secrets

```toml
ANTHROPIC_API_KEY = "..."
ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"

ADZUNA_APP_ID = "..."
ADZUNA_APP_KEY = "..."

JOOBLE_API_KEY = "..."
```

De app toont alleen bronnen waarvoor een geldige secret aanwezig is.

## Main file path

```text
app.py
```
