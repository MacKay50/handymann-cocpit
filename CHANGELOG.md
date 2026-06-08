# CHANGELOG — Håndværker Demo Platform

> **Formål:** Enkelt sted til at se hvad der er sket, hvad der er i gang, og hvad
> der kommer næst. Opdateres ved afslutning af hver session eller plan-fase.
>
> **Rollback:** Uden git bruges filernes `LastWriteTime` som tidsstempling.
> Initialiser git (`git init && git add . && git commit -m "baseline"`) for
> ægte rollback-mulighed — anbefales stærkt.

---

## AKTUEL STATUS — 2026-06-06

| Metric | Tal |
|--------|-----|
| Tests | 794 / 796 ✅ (2 pre-existing Plan B fejl) |
| Lint (ruff) | CLEAN ✅ |
| Type-check (mypy strict) | CLEAN ✅ |
| Sikkerhedsaudit | GODKENDT (2026-05-20) ✅ |
| Aktive planer | 3 (se nedenfor) |
| Versioner frigivet | v1.7 (2026-05-27) |

---

## IGANGVÆRENDE PLANER

### Plan C: Guided Intake Wizard
**Fil:** `plans/2026-06-06-guided-intake-wizard.md`
**Status:** Implementering i gang
**Formål:** Fullscreen 4-trins wizard — telefon-flow fra kundeoprettelse til tilbud og bekræftelsesmail uden at forlade siden.

| # | Fase | Status | Hvad der er gjort |
|---|------|--------|------------------|
| 1 | Backend foundation | ✅ DONE | `POST /quote-preparations/` (direkte, uden InboxMessage), `POST /wizard/cvr-lookup` (cvrapi.dk + graceful degrade), `wizard_service.py` (email-skabelon + send), 47 nye tests |
| 2 | Erfaringsbank-forslag | ✅ DONE | `POST /wizard/suggestions` (B1 keyword + B2 AI opt-in), CONT-10 fix: `similarity_search()` company-scopet, `HistoricalOffer.company_id` kolonne tilføjet, 32 nye tests |
| 3 | convert-to-flow udvidelse | ✅ DONE | Optional `source` param (default `email`, `phone` understøttet), optional `send_email`+`email_subject`+`email_body` — post-commit afsendelse, aldrig rollback ved fejl, 7 nye tests |
| 4 | Wizard frontend | ✅ DONE | `wizard.html` (fullscreen 4-trin, vanilla JS), `GET /wizard` route, "📞 Guided Intake" i nav.js sidebar, `data-smtp-status` + `data-wizard-step`, 3 nye tests |

---

### Plan A: UX/Logik-redesign — Cradle to Grave
**Fil:** `plans/2026-06-05-ux-cradle-to-grave-redesign.md`
**Status:** Godkendt — afventer implementering
**Formål:** Flytte `company_id` fra query/body-parametre til signed-cookie session,
plus 7 yderligere forbedringer (intake-flow, tilbudstyper, opgavekobling, påmindelser,
projekt-lukkekontrol, navigation, e-conomic sync).

| # | Fase | Kompleksitet | Status |
|---|------|-------------|--------|
| 1 | Session context + company middleware | HØJ | ⬜ Ikke startet |
| 2 | Model-felter + migration SQL | STANDARD | ⬜ Ikke startet |
| 3 | Unified Inbox + Guided Qualification | STANDARD | ⬜ Ikke startet |
| 4 | Tilbudstype-håndhævelse | STANDARD | ⬜ Ikke startet |
| 5 | TimeEntry opgave-kobling | STANDARD | ⬜ Ikke startet |
| 6 | Automatisk påmindelsesjob | STANDARD | ⬜ Ikke startet |
| 7 | Projekt-lukkekontrol | STANDARD | ⬜ Ikke startet |
| 8 | Navigation + e-conomic sync-panel + faktura-link | STANDARD | ⬜ Ikke startet |

> **Bemærk:** Plan A Phase 1 og Plan B Phase 1 overlapper på `companies.py` auth-fix
> (`RISK-02` / `DP-1`). Plan B løser dette delvist — koordiner rækkefølge.

---

### Plan B: Company Settings Drawer + Contact Directory
**Fil:** `plans/2026-06-06-company-settings-contact-directory.md`
**Status:** Draft — Phase 1 delvist implementeret (i nat kl. ~01:57)
**Formål:** UI til at redigere virksomhedsprofil + kontaktpersonsregister med søgning.
Løser to pre-existing bugs: PATCH auth-gap (HIGH severity) + `api()` credentials-fejl.

| # | Fase | Status | Hvad der er gjort |
|---|------|--------|------------------|
| 1 | Security-fix + ContactPerson model | 🟡 Delvist | Auth-guard på PATCH/DELETE companies + ContactPerson model + tests skrevet. Router og migration mangler. |
| 2 | `/contact-persons` router (CRUD + søgning) | ⬜ Ikke startet | |
| 3 | UI: Company-settings modal + Kontakter-fane | ⬜ Ikke startet | |

**Filer ændret i nat (2026-06-06 ~01:57):**
- `src/haandvaerker/api/companies.py` — PATCH/DELETE beskyttet med CompanyContextDep ownership-check (403 ved forsøg på at redigere anden virksomhed)
- `src/haandvaerker/models/contact_person.py` — ny model: ContactPerson, ContactPersonCreate, ContactPersonRead, ContactPersonUpdate
- `tests/test_companies_auth.py` — 4 tests: PATCH/DELETE egen virksomhed ✅, PATCH/DELETE anden virksomhed → 403 ✅
- `tests/test_model_contact_person.py` — 2 tests: felter og defaults ✅

**Mangler før Phase 1 er komplet:**
- `migrations/002_contact_person.sql` — CREATE TABLE contact_person
- `src/haandvaerker/models/__init__.py` — eksporter ContactPerson
- Registrer ContactPerson i `main.py` (via `create_all` eller migration)

---

## VERSIONS-HISTORIK

### v1.7 — 2026-05-27 (SENESTE FRIGIVNE)
**Invoice Monitoring + Betalingsradar**
- Faktura case-tracking: InvoiceCase, InvoiceDocument, InvoiceEvent, InvoiceActionItem, ExtractionEvidence
- InvoiceReminder med gebyrstyring (1./2./endelig rykker)
- Betalingsradar UI (`betalingsradar.html`)
- 660 tests total — alle grønne

### v1.6 — 2026-05-21
**Print / PDF + Eksport**
- `print.html` — professionelt PDF-dokument for tilbud og fakturaer
- `export.html` — universel eksport: CSV (BOM, semikolon) + XLSX server-side
- 9 XLSX-handlers (fakturaer, tilbud, projekter, kunder, medarbejdere, indbakke, frister, aftaler, erfaringsbank)
- Sorterbare kolonner, DA-format (dd/mm/yyyy + "1.234,56 kr")

### v1.5 — 2026-05-21
**Bankafstemning (Phase E)**
- BankTransaction import fra CSV (Danske Bank-format, SHA-256 dedup)
- EconomicInvoice sync fra e-conomic CSV
- ReconciliationMatch: deterministisk + AI + manuel matchtype
- `reconciliation.html` UI
- Sikkerhedsaudit bestået (SECURITY_AUDIT_2026-05-20.txt)

### v1.4 — 2026-05-21
**Erfaringsbank + MessageRouter (Phase D)**
- HistoricalOffer: import af lokale filer (PDF/DOCX/XLSX/TXT), godkend, søg
- Regelbaseret klassificering af indbakkebesked: 8 kategorier
- ActionItem tilstandsmaskine (open → in_progress → done/cancelled)
- CalendarSuggestion: godkend → opretter Aftale

### v1.3 — 2026-05-21
**Tilbudsgrundlag-flow (Phase C)**
- QuotePreparation: regelbaseret udtræk fra indbakke (telefon, adresse, opgavetype)
- `convert-to-flow`: opretter Kunde + Henvendelse + Projekt + Tilbud i ét kald
- Idempotent from-inbox/{id}

### v1.2 — 2026-05-20
**Dashboard + PDF-generering**
- Dashboard med 22 KPI-felter + kommende frister
- PDF-generering: faktura (ReportLab) + tilbud (ReportLab)
- Tilbudsaccept token-flow (offentlig `/accept?token=...`)

### v1.1 — 2026-05-20
**Intake + Kalender (Phase B)**
- AdminDeadline (Årshjul): VAT, løn, skatter — generate-year idempotent
- InboxMessage: indbakke med IMAP-integration (valgfri)
- Email-hent-knap i UI

### v1.0 — 2026-05-19
**Core flow-kobling (Phase A) + 13 CRUD-moduler**
- Enquiry → Project → Quote accept → Project active (automatisk)
- Alle 13 kernemoduler: Company, Customer, Employee, Project, Quote, TimeEntry, Expense, Invoice, Payment, Appointment, Reminder, AdminDeadline, Salary, VatPeriod
- UI: Single-page app med 8 faner (dashboard, kunder, projekter, tilbud, fakturaer, medarbejdere, indbakke, kalender)
- 25% moms server-side (Decimal ROUND_HALF_UP på alle beregninger)
- Blød sletning (soft-delete) overalt — append-only på fakturaer/betalinger/løn

---

## KENDT TEKNISK GÆLD (FU-liste)

| ID | Beskrivelse | Prioritet |
|----|-------------|-----------|
| FU-P1 | Auto-reverse ved deaktivering af betaling (konservativt valg: ingen auto-reverse) | Lav |
| FU-P2 | Fuld idempotent POST for betalinger (samme id → 200) | Lav |
| FU-12 | Direkte udlæg→faktura-kobling (uden om projekt) | Lav |
| FU-13 | Godkendelsesflow for udlæg (hvem godkender?) | Åbent spørgsmål |
| FU-14 | Kvitteringsbillede-upload (storage-strategi TBD) | Åbent spørgsmål |
| FU-MIN | Konsolider `_require_active_project()` — duplikeret i 5 routere | Lav |
| FU-KS | `keyword_search()` accepterer `company_id` men filtrerer ikke på det — separat cross-company leak (opdaget i Phase 2, ikke i scope) | MEDIUM |
| FU-MIGR | `ALTER TABLE historicaloffer ADD COLUMN company_id TEXT REFERENCES company(id)` migration mangler til produktion (`migrations/002_historical_offer_company_id.sql`) | MEDIUM |
| FU-SMTP-STATUS | `/session/smtp-status` endpoint mangler — `data-smtp-status` i wizard.html er statisk `"unknown"`, pre-flight SMTP-advarsel vises aldrig (post-submit fejl vises korrekt) | LAV |
| RISK-02 | `PATCH /companies/{id}` auth-gap — **delvist løst i nat** (se Plan B) | ~~HIGH~~ → løst |
| RISK-03 | Påmindelses-crash-vindue: SMTP-send sker før commit | Accepteret/dokumenteret |

---

## PROCESGUIDE — Sådan holder vi CHANGELOG opdateret

1. **Ved session-start:** Læs `AKTUEL STATUS` og `IGANGVÆRENDE PLANER`.
2. **Under arbejde:** Opdater fase-status fra ⬜ → 🟡 → ✅ efterhånden som faser afsluttes.
3. **Ved session-slut:** Tilføj hvad der blev lavet under den relevante plan-fase.
4. **Ved ny version:** Flyt igangværende plan til `VERSIONS-HISTORIK` med dato og kort beskrivelse.
5. **Rollback:** Brug filernes `LastWriteTime` + denne CHANGELOG til at forstå hvilke filer der skal gendannes. Med git: `git log` + `git revert <commit>`.

---

*Sidst opdateret: 2026-06-06 (session-start)*
