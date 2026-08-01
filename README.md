# Loopbaan-Agent Lite 2.0

Definitieve Lite-basis met:

- lokale documentverwerking;
- verplichte Anthropic tool-output in plaats van vrije JSON;
- één Profiler-call;
- één gecachete Explorer-call;
- lokale vacaturevoorselectie;
- Matcher in batches van maximaal vijf vacatures;
- Coach alleen op verzoek;
- deterministische feedbackverwerking;
- SQLite-resultaatcache;
- Streamlit-cache voor Adzuna.

## Bestanden

```text
app.py
core.py
requirements.txt
README.md
```

## Streamlit secrets

```toml
ANTHROPIC_API_KEY = "..."
ADZUNA_APP_ID = "..."
ADZUNA_APP_KEY = "..."

# Alleen nodig wanneer je een ander werkend Anthropic-model wilt gebruiken:
ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"
```

## Main file path

```text
app.py
```
