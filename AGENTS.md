# AGENTS.md — Håndværker Business System

> Read `vision.md` first for the product north star. This file is the technical kickstart.

## What this repo is

Et REST API til intern styring af en lille håndværkervirksomhed. Én service:

- **API-service** (`src/haandvaerker/`) — FastAPI på port 8000. SQLite-database
  (fil: `haandvaerker.db`). Håndterer kunder, projekter, tilbud, tidsregistrering,
  udlæg, fakturaer, møder og løngrundlag.

Ingen frontend i dette repo endnu — API'et drives af en fremtidig PWA og webgrænseflade.

---

## Tech stack

| Layer          | Technology              | Version / notes                                    |
|----------------|-------------------------|----------------------------------------------------|
| **API**        | Python + FastAPI        | Python 3.11+, FastAPI 0.110+                       |
| **ORM**        | SQLModel                | 0.0.16+ — kombinerer SQLAlchemy + Pydantic         |
| **Database**   | SQLite                  | Fil-baseret. Migrationer via Alembic.              |
| **Validering** | Pydantic v2             | **IKKE v1** — breaking changes i v2 er relevante  |
| **Test**       | pytest + httpx          | `pytest-asyncio` til async endpoints              |
| **Lint**       | ruff                    | `ruff check` + `ruff format`                       |
| **Typecheck**  | mypy                    | strict mode                                        |
| **Package mgr**| pip + pyproject.toml   | Brug `pip install -e ".[dev]"` til setup           |

> **Pydantic v2 advarsel:** `model.dict()` er fjernet — brug `model.model_dump()`.
> `validator` decorator er fjernet — brug `field_validator`. Agents: vær eksplicit.

---

## Repository layout

```
haandvaerker-demo/
  src/haandvaerker/        Applikationskode
    main.py                FastAPI app-instans, lifespan, router-registrering
    config.py              Settings (database-sti, miljøvariabler)
    database.py            SQLModel engine + get_session dependency
    api/                   Route-handlers, én fil per ressource
      customers.py         CRUD for kunder
      projects.py          CRUD for projekter
      quotes.py            Tilbud
      time_entries.py      Tidsregistrering
      expenses.py          Udlæg
      invoices.py          Fakturaer
      meetings.py          Møder og aftaler
      employees.py         Medarbejdere og løngrundlag
    models/                SQLModel table-modeller + Pydantic schemas
      customer.py
      project.py
      quote.py
      time_entry.py
      expense.py
      invoice.py
      meeting.py
      employee.py

  tests/                   pytest-tests, spejler src-struktur
    conftest.py            In-memory SQLite + TestClient setup
    test_customers.py
    test_projects.py
    ...

  alembic/                 Database-migrationer
  alembic.ini
  pyproject.toml
  plans/                   Plan-artefakter (committed)
  research/                Forskningsartefakter (gitignored)
  docs/notes/              Agent-noter (gitignored)
```

---

## How to build and run

### Prerequisites

- Python 3.11+
- pip

### Local development

```bash
pip install -e ".[dev]"          # én gang — installerer app + dev-afhængigheder
uvicorn src.haandvaerker.main:app --reload   # start dev-server på port 8000
```

API-dokumentation: http://localhost:8000/docs (Swagger UI, automatisk fra FastAPI)

### Database

```bash
alembic upgrade head             # kør alle migrationer (opretter haandvaerker.db)
alembic revision --autogenerate -m "beskrivelse"   # ny migration efter model-ændring
```

SQLite-filen (`haandvaerker.db`) er gitignored. Test bruger in-memory SQLite.

---

## How to test

### Fast unit + integration tests

```bash
pytest                           # kør alle tests
pytest tests/test_customers.py  # kør én test-fil
pytest -x                       # stop ved første fejl
```

### Lint

```bash
ruff check src/ tests/           # lint (substance rules: se nedenfor)
ruff format --check src/ tests/  # format-tjek
```

### Typecheck

```bash
mypy src/haandvaerker/
```

### Linter ratchet

Net-nye linjer skal være rene på **substance rules**:

- `E711` — sammenligning med None (brug `is None`)
- `E722` — bare `except:` uden exception-type
- `F841` — lokal variabel tildelt men aldrig brugt
- `F401` — ubrugt import
- `B006` — mutable default argument
- `B007` — loop-variabel ikke brugt i loop-krop
- `S106` — hardkodet password
- `RUF100` — ubrugt `# noqa`-kommentar

Kør `ruff check --select E711,E722,F841,F401,B006,B007,S106,RUF100 src/ tests/`
for substance-only tjek. Ingen nye findings på net-nye linjer — nogensinde.

---

## Data model (overordnet)

```
Customer (kunde)
  └── Project (projekt)          ← alt data hæftes her
        ├── Quote (tilbud)       status: draft|sent|accepted|rejected|expired
        ├── TimeEntry (time)     dato, medarbejder, timer, beskrivelse
        ├── Expense (udlæg)      dato, beløb, moms, bilag-reference
        ├── Invoice (faktura)    append-only, status: draft|sent|paid|credited
        ├── Meeting (møde)       tidspunkt, sted, deltagere, referat
        └── Document (dokument)  fil-reference, type, dato

Employee (medarbejder)           lønsats, rolle, ansættelsesdato
  └── TimeEntry                  medarbejder ↔ projekt M:N via time-entries
```

**ID-format:** alle primærnøgler er UUIDs (string). Aldrig auto-increment integers
på ressourcer der synkroniseres fra PWA (idempotens-krav).

---

## Architecture

### Request lifecycle

```
HTTP request
  → FastAPI router (api/<resource>.py)
    → Pydantic validering (models/<resource>.py)
      → Service-lag (inline i router — simpel app, ingen ekstra lag)
        → SQLModel / SQLite
          → Pydantic response-model (aldrig rå ORM-objekt til klienten)
```

### Momsberegning

Moms beregnes altid af kode: `moms = beloeb_ekskl * Decimal("0.25")`.
Aldrig sendt fra klient og accepteret ukritisk. Klienten sender `beloeb_ekskl`;
API'et returnerer `beloeb_ekskl`, `moms`, `beloeb_inkl`.

### Faktura-livscyklus (append-only)

```
draft → sent → paid
             → credited (ny kredit-faktura oprettes, original uændret)
```
Ingen UPDATE på `status`-felter for fakturaer — kun INSERT af ny tilstand-række
eller ny kredit-faktura.

---

## Key design rules

1. **Kunden er omdrejningspunktet** — se `vision.md §1`. Ingen ressource uden
   `project_id`. Valider FK ved oprettelse; fejl eksplicit.

2. **Fejl er synlige** — se `vision.md §3`. Ingen `amount = data.get("amount", 0)`.
   Manglende påkrævede felter → 422 med feltnavn i fejlbesked.

3. **Revisionsspor** — se `vision.md §4`. `Invoice`, `Payment`, `SalaryEntry`:
   ingen fysisk DELETE, ingen UPDATE af beløbsfelter. Korrektioner via ny post.

4. **Følsomme felter maskeres** — se `vision.md §6`. `Employee.cpr_number` og
   `Customer.cvr_number` returneres aldrig i klartekst fra GET-endpoints.
   Response-modeller har eksplicit `cpr_masked: str` i stedet.

5. **Moms beregnes af kode** — aldrig antaget fra klient-input. Se §Momsberegning.

6. **UUID-idempotens** — klienten må sende `id` (UUID) ved POST. Hvis ID allerede
   eksisterer og data matcher → 200 (idempotent). Hvis data afviger → 409.

7. **Ingen ORM-objekter direkte i response** — altid via Pydantic response-model.
   Undgår accidentel eksponering af interne felter.

8. **Design for nem ændring** — se `vision.md §7`. Policy (momsregler, faktura-
   tilstande) i egne funktioner/konstanter, ikke inline i route-handlers.

---

## High-stakes paths (altid RPIR — aldrig simple-change)

- `src/haandvaerker/api/invoices.py` — fakturering og kreditering
- `src/haandvaerker/api/employees.py` — løngrundlag og CPR-data
- `src/haandvaerker/models/invoice.py` — faktura-datamodel
- `alembic/versions/` — alle migrationer
- Enhver kode der beregner beløb, moms eller løn

---

## Simple-change workflow

**Triviel = ALLE disse er sande:**
- Net diff under ~50 linjer.
- Én fil eller få tæt koblede filer i samme subsystem.
- Rører IKKE high-stakes paths ovenfor.
- Indfører ikke ny endpoint, config-nøgle eller migration.
- Ingen adfærdsændring eksponeret eksternt.

**Typiske trivielle ændringer:** doc-typos, kommentarfix, rename lokal variabel,
stramme type-hint, lint-nudge på rørte linjer, test-assertion-tweaks.

**Hvis noget af ovenstående er falsk → Tab til `develop-conductor`.**

---

## Environment variables

| Variable         | Default              | Purpose                                    |
|------------------|----------------------|--------------------------------------------|
| `DATABASE_URL`   | `sqlite:///./haandvaerker.db` | Database connection string        |
| `SECRET_KEY`     | (påkrævet i prod)    | JWT-signering (fremtidigt auth-modul)      |
| `ENV`            | `development`        | `production` aktiverer ekstra sikkerhed    |
| `LOG_LEVEL`      | `INFO`               | Python logging-niveau                      |

`.env.example` leveres med safe placeholders.

---

## Adding a new resource

1. Opret `src/haandvaerker/models/<resource>.py` med SQLModel table + Pydantic schemas.
2. Opret `src/haandvaerker/api/<resource>.py` med FastAPI router og CRUD-endpoints.
3. Registrer router i `src/haandvaerker/main.py`.
4. Skriv `alembic revision --autogenerate -m "<resource>-table"`.
5. Skriv tests i `tests/test_<resource>.py`.

## AI agent infrastructure (`.claude/`)

Se `CLAUDE.md` for harness-beskrivelse. Kort version:

| Agent               | Rolle                                                   |
|---------------------|---------------------------------------------------------|
| `develop-conductor` | RPIR workflow for ikke-trivielle ændringer              |
| `review-conductor`  | Read-only audits (pre-PR, sikkerhed, release)           |

Subagents: `researcher`, `planner`, `plan-verifier`, `implementer`, `phase-verifier`, `reviewer`.
