# Loopbaan\-Agent 3\.0\.2

Rate\-limit\-veilige multi\-source search\.

## Verbeteringen

- Adzuna gebruikt maximaal vijf zoektermen per zoekactie\.
- Adzuna\-verzoeken lopen sequentieel met 2,6 seconden ertussen\.
- Bij HTTP 429 stopt alleen Adzuna; Jooble gaat door\.
- Bij tijdelijke 5xx\-fouten doet Adzuna maximaal één rustige retry\.
- Jooble zoekt onafhankelijk en beperkt parallel\.
- Technische URL’s, queryparameters en API\-sleutels verschijnen niet meer in foutmeldingen\.
- Zoekdiagnostiek is leesbaar en toont geen ruwe JSON\.
- Knop om de zoekcache handmatig te wissen\.

## Updaten vanaf 3\.0\.1

Vervang:

- `app.py`
- `sources.py`
- `README.md`

De overige bestanden blijven gelijk\.

## Belangrijk

Wanneer een API\-sleutel eerder zichtbaar is geworden in een screenshot of log,
vervang die sleutel bij de betreffende aanbieder en werk Streamlit Secrets bij\.
