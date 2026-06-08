# Håndværker Business System — Kom i gang

## Forudsætninger

- **Python 3.9 eller nyere** — tjek med `python --version`
- **pip** — følger normalt med Python

---

## Trin 1 — Installér afhængigheder

Åbn en terminal i projektmappen og kør:

```
pip install -e ".[dev]"
```

Dette installerer FastAPI, uvicorn, SQLModel, ReportLab og testværktøjer.
Skal kun gøres én gang.

---

## Trin 2 — Start serveren

**Nemmest:** Dobbeltklik på `start.bat`

Eller i terminalen:

```
python -m uvicorn haandvaerker.main:app --reload
```

Serveren starter på **http://127.0.0.1:8000**
Browseren åbner automatisk på forsiden.
Stop serveren med **Ctrl+C**.

---

## Trin 3 — Seed demo-data (valgfrit)

For at se systemet med realistiske data:

**Nemmest:** Dobbeltklik på `seed_demo.bat` (mens serveren kører)

Eller i terminalen:

```
python seed_demo.py
```

Dette opretter 3 virksomheder med komplet demo-data inkl. bankafstemning og fuld pipeline.

**Valgfrit — brug dine egne CSV-filer:**

```
python seed_demo.py --bank-csv C:\Afstemning\bank.csv ^
                    --invoice-csv C:\Afstemning\fakturaer.csv ^
                    --customer-csv C:\Afstemning\kunder.csv
```

Uden parametre bruges fixture-filer. Se `python seed_demo.py --help` for detaljer.

Scriptet printer links til alle tre virksomheder til sidst.

---

## Trin 4 — Udforsk systemet

| URL | Beskrivelse |
|-----|-------------|
| http://127.0.0.1:8000 | Forside med demo-flow oversigt |
| http://127.0.0.1:8000/docs | **Swagger UI** — test alle endpoints direkte i browseren |
| http://127.0.0.1:8000/redoc | Læsevenlig API-dokumentation |

---

## Vigtige ting at vide

**Databasen** gemmes i `haandvaerker.db` i projektmappen.
Den oprettes automatisk første gang serveren starter.

**Nulstil data** ved at slette `haandvaerker.db` og køre `seed_demo.bat` igen.

**Alle endpoints kræver `company_id`** — find den i Swagger under `GET /companies/`
eller brug den som scriptet printer.

---

## Demo-flow: Fra tilbud til betalt faktura

1. `POST /companies/` — opret din virksomhed
2. `POST /customers/` — opret en kunde
3. `POST /projects/` — opret et projekt
4. `POST /quotes/` — opret tilbud med linjer
5. `POST /quotes/{id}/send` — send tilbud
6. `POST /quotes/{id}/accept` — accepter → faktura-kladde oprettes automatisk
7. `GET /quotes/{id}/pdf` — download tilbuds-PDF
8. `POST /invoices/{id}/send` — send faktura til kunde
9. `GET /invoices/{id}/pdf` — download faktura-PDF
10. `POST /invoices/{id}/pay` — marker som betalt

---

## Demo-flow: Saml timer og udgifter på en faktura

1. `POST /time-entries/` — registrer timer (billable: true)
2. `POST /expenses/` — registrer udgifter
3. `POST /invoices/draft-from-project` — saml alt ubillede til én kladde
4. Fortsæt fra trin 8 ovenfor

---

## Demo-flow: Bankbekræftelse og historisk kundedata (fuld pipeline)

1. `POST /bank-transactions/import` — importer bankudtog CSV (DD-MM-YYYY **eller** DD.MM.YYYY)
2. `POST /economic-invoices/import` — importer e-conomic faktura-eksport CSV
3. `POST /reconciliation/match` — auto-afstem bank ↔ fakturaer
4. `POST /economic-invoices/derive-customers` — udled kunder fra fakturanavne
5. `POST /economic-invoices/create-historical-projects` — opret afsluttede projekter for bankbekræftede fakturaer

Alternativt: importer kundekartotek direkte fra e-conomic CSV:

```
POST /economic-customers/import?company_id=...&file_path=C:\kunder.csv
POST /economic-customers/sync-all?company_id=...
```

**Repeat-job** (tilbagevendende kunde):
```
POST /customers/{id}/repeat-job?title=Malerarbejde+2026
```
Opretter projekt + tilbudskladde i én kald.

---

## Rapporter

Alle rapporter returnerer JSON som standard.
Tilføj `&format=csv` for at downloade som CSV (åbner direkte i Excel).

```
GET /reports/revenue?company_id=…&year=2026&group_by=month
GET /reports/project-profitability?company_id=…
GET /reports/employee-hours?company_id=…&from_date=2026-01-01&to_date=2026-12-31
GET /reports/top-customers?company_id=…&year=2026&limit=10
GET /reports/expense-breakdown?company_id=…&year=2026
```

---

## Tests

Kør den fulde testsuite:

```
python -m pytest -q
```

683 tests — alle grønne.
