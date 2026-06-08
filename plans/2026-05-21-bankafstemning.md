# Plan: Bankafstemningsmodul (Scenarie B)

**Path:** plans/2026-05-21-bankafstemning.md
**Created:** 2026-05-21
**Research:** research/2026-05-21-bankafstemning/
**Status:** approved

---

## Research anchors

All artifacts under `research/2026-05-21-bankafstemning/` are gitignored;
regenerate with `develop-conductor` if missing.

- `research/2026-05-21-bankafstemning/meta.json` — slug, three researchers
  (code+contract, impact+risk, options), brief path, plan path.
- `research/2026-05-21-bankafstemning/brief.md` — synthesised brief with the
  five user-resolved decisions: file_path query param (DP-1),
  many-to-many cardinality (DP-2), Danske Bank canonical CSV (DP-3),
  dashboard KPI tile in v1 (DP-4), manual matching trigger (DP-5).
- `research/2026-05-21-bankafstemning/researcher-1-code-contract.json` —
  findings `CODE-01..10` (UUID/soft-delete/enum/SessionDep/router conventions,
  no existing CSV code, no Danish parsers, no UploadFile pattern) and
  `CONT-01..10` (field shapes for the three new models, request/response
  contracts for the eight new endpoints, test fixture pattern).
- `research/2026-05-21-bankafstemning/researcher-2-impact-risk.json` —
  findings `IMPACT-01..05` (purely additive schema, Payment vs
  ReconciliationMatch overlap risk, dashboard fields are additive,
  conftest `create_all` auto-discovers new tables) and `RISK-01..09`
  (CSV injection, duplicate-import deduplication, amount precision,
  AI auto-confirm, company isolation, all-or-nothing import, encoding,
  LM-Studio port heuristic).
- `research/2026-05-21-bankafstemning/researcher-3-options.json` — five
  selected options: `OPT-B` (deterministic-first + AI supplement),
  `OPT-C` (single drop zone + type dropdown), `OPT-D` (invoice-centric
  reconciliation table), `OPT-E` (nullable project_id FK, manual link),
  `OPT-F` (badges in view + KPI tiles on Overblik dashboard).

Phases below cite specific finding IDs (`CODE-03`, `CONT-06`, `RISK-02`,
`OPT-B`, ...) — the reader resolves those against the JSONs above.

---

## Problem

The accountant ("regnskabsdame") today has no way inside haandvaerker to see
which e-conomic-invoiced sales have actually been paid into the company's
bank account. The two CSV exports the user already has on disk
(Danske-Bank-formatted bank statement, e-conomic faktura-eksport) must be
imported, deduplicated, reconciled, and surfaced in an invoice-centric
"kræver handling" view plus an Overblik dashboard summary. Reconciliation
is matched by deterministic amount-and-date rules first, AI-supplemented
only for the residual, and never auto-confirmed beyond a deterministic
exact match. The change introduces the first CSV-ingest path in this
codebase; the highest-severity design risks the brief enumerates
(duplicate import corrupting totals — `RISK-02`, float-vs-øre precision —
`RISK-03`, AI auto-confirm bypassing Iron Law 3 — `RISK-04`, cross-company
write — `RISK-06`, partial-batch import — `RISK-07`, Danish CSV encoding —
`RISK-08`) are all addressed at the import boundary and the matching
service rather than in the model layer.

## Approach

Three new tables (`BankTransaction`, `EconomicInvoice`, `ReconciliationMatch`)
appended to `SQLModel.metadata` (`IMPACT-01`, `IMPACT-04`) — picked up
automatically by both `database.create_db_and_tables()` and
`tests/conftest.py:17` `SQLModel.metadata.create_all`. Two CSV import
endpoints follow the existing `historical_offers.py:44` `file_path: str`
query-param pattern (`CODE-04`, user decision DP-1) and write integer-øre
amounts (`RISK-03`) parsed from Danish notation (`1.234,56` → 123456).
Deduplication is enforced at the database layer by a unique constraint on
`BankTransaction.import_hash` (SHA-256 of normalised content) and on
`(company_id, economic_invoice_number)` for `EconomicInvoice`
(`RISK-02`). All-or-nothing validation runs before any insert
(`RISK-07`), 422 with row-level errors on failure. A
`reconciliation_service.py` runs deterministic matching first (exact
amount-øre + date ±7d → auto-confirmed) and, only when
`local_ai.is_enabled()` returns True, asks Ollama to rank candidates for
the residual into proposed (`confirmed=False`) matches the accountant
must explicitly confirm — `OPT-B`, Iron Law 3. The frontend is one new
`reconciliation.html` static page following the `export.html` toolbar /
table / badge primitive (`OPT-D` + `OPT-F`); the Overblik dashboard gains
three additive fields (`OPT-F`). All five user-resolved DP decisions
(`file_path`, many-to-many, Danske Bank canonical, dashboard in v1,
manual trigger) are baked in.

## Architectural posture

**Extending the incumbent pattern.** The incumbent pattern is: one
router module per resource (`api/<name>.py`) with a local
`SessionDep = Annotated[Session, Depends(get_session)]` alias
(`CODE-06`), one SQLModel module per resource (`models/<name>.py`)
with `(str, Enum)` enums, UUID-str PKs, soft-delete via
`active: bool` (`CODE-01`, `CODE-02`, `CODE-03`), tenant scoping
via `company_id: str = Field(foreign_key="company.id")` (`CODE-08`),
and dashboard reads as additive fields on `DashboardRead`
(`IMPACT-03`). The options-researcher surfaced no redesign of that
spine — `OPT-A..F` are all in-pattern selections. The single
genuinely-new shape is the CSV-import boundary, which the brief
constrains to follow `historical_offers.py:44`'s `file_path: str`
query-param convention (DP-1).

We pick extension over redesign because:

- **Separation of concerns** is preserved. Transport (`api/*.py`)
  stays separate from data shape (`models/*.py`) and from
  decision logic. A new `services/danish_csv.py` isolates
  format-specific parsing (Danske-Bank date `DD-MM-YYYY`,
  `1.234,56`-style amount, UTF-8 → CP-1252 fallback per
  `RISK-08`) away from both transport and matching. A new
  `services/reconciliation_service.py` isolates matching policy
  (deterministic threshold, AI residual handling, confirmation
  rules per `RISK-04`) away from both the API surface and
  storage. Policy (when to call Ollama; what counts as a match)
  lives next to the data it decides on; mechanism (HTTP
  transport, JSON parsing) stays in `services/local_ai.py`
  unchanged.
- **Pick-up-ability.** A new engineer reading the diff finds:
  one `api/<bank|economic|reconciliation>.py` per concern with
  the same local `SessionDep` shape they already know; one
  `models/<bank_transaction|economic_invoice|reconciliation_match>.py`
  per concern with the same `(str, Enum)` + `active: bool`
  shape; the registration line in `main.py:81-106` extends the
  same `app.include_router(...)` list; the static page sits next
  to `export.html`. Sub-10-minute orientation, no new
  conventions to absorb.
- **Extensibility.** The next related change — supporting a
  second bank format (Nordea / Jyske) — extends one parser
  module (`services/danish_csv.py`) with a `bank_format` switch
  (already foreseen in `CONT-04`). The next change after that —
  haandvaerker `Invoice` ↔ `EconomicInvoice` linking — adds a
  nullable FK without touching reconciliation logic. Both are
  one-file changes after this plan lands.
- **Security / stability posture.** Three new failure modes are
  added: cross-company CSV submission (`RISK-06` — mitigated by
  `Company.get` check before any write), duplicate import
  (`RISK-02` — mitigated by unique constraint, IntegrityError
  → 409), and AI hallucinating a wrong invoice match (`RISK-04`
  — mitigated by `confirmed=False` on every `auto_ai` match,
  human confirm required). No existing invariant is weakened.
  Iron Law 2 is preserved: row-level CSV errors raise 422 with
  the full error list — no silent skip (`RISK-07`); encoding
  failure raises 422 — no silent mojibake (`RISK-08`).

**Debt accrued by extending.** The Payment ↔ ReconciliationMatch
conceptual overlap (`IMPACT-02`) is real but explicitly out of
scope per the brief's "Resolved Questions" — a
`haandvaerker.Invoice` is not linked to an `EconomicInvoice`, and
`ReconciliationMatch` does not update `Invoice.status`. The plan
documents this in endpoint docstrings (Phase 3) so the next
engineer does not silently bridge the two systems. Tracking
marker: a `# NOTE: see plans/2026-05-21-bankafstemning.md §"Out of
scope" — Invoice<->EconomicInvoice link is a separate plan`
comment at the top of `api/reconciliation.py`.

## Code-minimalism subtraction check

Plan-level: is there a version of this work that achieves the
goal by deletion rather than addition? No — three new tables, two
new CSV import paths, one new matching service, one new view, and
three additive dashboard fields are all new surface for a
greenfield capability. The codebase has no dead reconciliation
code to remove (confirmed by `CODE-04`: "no CSV parsing code
anywhere"). The plan is therefore mostly additive; the cleanup
discipline appears at the phase level:

- Phase 1 deletes nothing (greenfield models).
- Phase 2 deletes nothing (greenfield endpoints) but introduces
  one shared parser module (`services/danish_csv.py`) so Phase 4
  / future bank formats avoid duplicating parsers — net long-run
  subtraction by anti-duplication.
- Phase 3 deletes nothing in source but removes a placeholder
  endpoint stub written in Phase 2 if it exists.
- Phase 4 replaces the v1 `export.html` static-page approach with
  a sibling `reconciliation.html` — no deletion in `export.html`.
- Phase 5 updates `test_dashboard.py` in place: the assertion
  field list at `test_dashboard.py:34-40` is **extended** with
  three reconciliation fields, not replaced. The plan flags
  Phase 5 as a pure-addition phase by design (no production code
  deleted, only tests added) — appropriate for a test-completion
  phase.

The plan is flagged as pure-addition across phases 1, 2, 3, 5 and
mostly-addition in phase 4. Phase-verifier will warn on net LoC;
the justification is the greenfield scope per `CODE-04` and
`IMPACT-01`.

## Invariants preserved

- **Iron Law 1 — ask the user on ambiguity.** All five `DP-*`
  open questions were resolved by the user before plan write
  (see brief.md §"User-Resolved Design Decisions").
- **Iron Law 2 — fail loud.** CSV row errors return 422 with the
  full row-level error list (`RISK-07`); encoding failures
  return 422 (`RISK-08`); duplicate-import returns 409 on
  IntegrityError (`RISK-02`); cross-company writes return 422
  with `Company '<id>' not found` (`RISK-06`, matches
  dashboard's pattern at `api/dashboard.py:28-29`); Ollama
  unavailable yields a `None` return from `local_ai.chat_completion`
  which the matching service treats as "no AI residual matches
  this run" (not as a silent successful match).
- **Iron Law 3 — code decides.** Deterministic matcher (Python,
  not LLM) makes every confirmed match. AI returns ranked
  candidates; deterministic confidence-threshold gate decides
  whether to even propose them; user confirm is the only path
  to `confirmed=True` for `auto_ai` matches (`RISK-04`, `OPT-B`).
- **Amount precision (`RISK-03`).** All three new models store
  amounts as integer øre. Float never appears in any new model
  field. CSV parsing converts at the boundary; the
  reconciliation matcher compares `==` on int, never `< epsilon`
  on float.
- **company_id scoping (`CODE-08`, `RISK-06`).** Every new
  multi-tenant table carries `company_id` FK. Every list
  endpoint filters on `company_id`. Every import endpoint
  validates `Company.get(company_id)` before the first write.
  Cross-company `ReconciliationMatch` is rejected in
  `manual-match` (Phase 3) by re-reading both sides.
- **Soft-delete via `active: bool` (`CODE-02`).** All three new
  models carry `active`; `ReconciliationMatch.reject` flips
  `active=False`, never hard-deletes. List endpoints accept
  `active_only: bool = True` (default).
- **Fixed-path routes precede path-parameter routes (`CODE-09`).**
  `/reconciliation/manual-match`, `/reconciliation/match` are
  registered before `/reconciliation/{match_id}/confirm` and
  `/reconciliation/{match_id}/reject`.
- **Existing 230-test suite stays green (`IMPACT-04`).** New
  models use defaulted / nullable columns only (no required new
  column without default); `conftest.py:17`'s
  `SQLModel.metadata.create_all(engine)` picks up the three new
  tables without conftest change.
- **Dashboard payload contract (`IMPACT-03`).** Existing
  `DashboardRead` fields are not removed or renamed; three new
  fields are appended. The assertion at `test_dashboard.py:34-40`
  is updated, not replaced.

---

## Phases

### Phase 1: Models, enums, and metadata registration

**Goal.** Add the three new SQLModel table classes
(`BankTransaction`, `EconomicInvoice`, `ReconciliationMatch`),
their enums (`BankTransactionStatus`, `EconomicInvoiceStatus`,
`MatchType`), and Read/Create schemas — and prove the existing
test suite still passes after `SQLModel.metadata.create_all`
picks them up. No endpoints, no parsers, no business logic in
this phase.

**Anchors.** `CODE-01` (UUID str PK), `CODE-02` (`active: bool`),
`CODE-03` (`(str, Enum)` lowercase), `CODE-08` (company_id FK),
`CODE-10` (date vs datetime), `CONT-01` (BankTransaction fields),
`CONT-02` (EconomicInvoice fields), `CONT-03` (ReconciliationMatch
fields + many-to-many decision per DP-2), `RISK-02` (unique
constraint on `BankTransaction.import_hash` and on
`(company_id, economic_invoice_number)`), `RISK-03` (integer øre,
no float), `IMPACT-01` (purely additive), `IMPACT-04` (conftest
auto-discovers).

**Files.**
```
src/haandvaerker/models/bank_transaction.py        (new)
src/haandvaerker/models/economic_invoice.py        (new)
src/haandvaerker/models/reconciliation_match.py    (new)
src/haandvaerker/models/__init__.py                (re-export only)
tests/test_reconciliation_models.py                (new)
```

These are the ONLY paths the implementer may touch in this phase.
No `main.py` edit yet (no routers to register), no
`database.py` edit (`create_db_and_tables` already calls
`SQLModel.metadata.create_all`).

**Dependencies.** None — pure greenfield additions.

**Acceptance criteria.**

1. `python -m pytest tests/ -v` passes the full existing suite
   plus the new `tests/test_reconciliation_models.py` with zero
   regressions.
2. `python -c "from haandvaerker.models.bank_transaction import BankTransaction, BankTransactionStatus; from haandvaerker.models.economic_invoice import EconomicInvoice, EconomicInvoiceStatus; from haandvaerker.models.reconciliation_match import ReconciliationMatch, MatchType; assert BankTransactionStatus.unmatched.value == 'unmatched' and EconomicInvoiceStatus.matched.value == 'matched' and MatchType.auto_exact.value == 'auto_exact'"` exits 0.
3. `python -c "from sqlmodel import SQLModel, create_engine; from sqlmodel.pool import StaticPool; from haandvaerker.models.bank_transaction import BankTransaction; from haandvaerker.models.economic_invoice import EconomicInvoice; from haandvaerker.models.reconciliation_match import ReconciliationMatch; e = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool); SQLModel.metadata.create_all(e); print('OK')"` exits 0 with `OK` (proves no migration conflict, all FKs resolvable).
4. `python -c "from haandvaerker.models.bank_transaction import BankTransaction; cols = {c.name for c in BankTransaction.__table__.columns}; assert 'amount_ore' in cols and 'import_hash' in cols and 'company_id' in cols and 'active' in cols, cols"` exits 0.
5. `python -c "from haandvaerker.models.bank_transaction import BankTransaction; col = BankTransaction.__table__.columns['amount_ore']; assert str(col.type).upper().startswith('INTEGER'), str(col.type)"` exits 0 (proves integer-øre, not float — `RISK-03`).
6. `python -c "from haandvaerker.models.bank_transaction import BankTransaction; col = BankTransaction.__table__.columns['import_hash']; assert col.unique is True, 'import_hash must be UNIQUE'"` exits 0 (`RISK-02`).
7. `python -c "from haandvaerker.models.economic_invoice import EconomicInvoice; idxs = [tuple(sorted(c.name for c in idx.columns)) for idx in EconomicInvoice.__table__.indexes if idx.unique]; assert ('company_id', 'economic_invoice_number') in idxs or any(set(t) >= {'company_id', 'economic_invoice_number'} for t in idxs), idxs"` exits 0 (`RISK-02`).
8. `python -c "from haandvaerker.models.reconciliation_match import ReconciliationMatch; idxs = [tuple(sorted(c.name for c in idx.columns)) for idx in ReconciliationMatch.__table__.indexes if idx.unique]; assert not any('bank_transaction_id' in t and len(t) == 1 for t in idxs), 'no single-column unique on bank_transaction_id — many-to-many per DP-2'"` exits 0 (`CONT-03`, DP-2).
9. The new `tests/test_reconciliation_models.py` contains at least: one test that creates and persists a `BankTransaction` with `amount_ore=123456` and re-reads it (proves int round-trip); one test that asserts a second insert with the same `import_hash` raises `sqlalchemy.exc.IntegrityError`; one test that asserts inserting two `ReconciliationMatch` rows sharing the same `bank_transaction_id` succeeds (many-to-many).

**Deletions.**

- None. Greenfield phase. Empty by design.

**Subtraction check.** Can this phase be achieved purely by
deletion? No — the three tables do not exist and cannot be
synthesised by deleting code. Net add ~180 lines (three models
~40 lines each, one test file ~60 lines, one `__init__.py`
re-export line).

**Pure-addition flag.** Yes. Justification: greenfield model
slice for a new capability; no existing reconciliation code to
subtract from.

**Rollback.** `git revert <sha>` removes the three model files
and the test file. No `main.py` change to undo, no router
registration to undo, no migration file to roll back (the
codebase has no Alembic — `create_db_and_tables` simply does not
emit the new tables on the next startup once the imports are
gone). Existing DBs with the new tables already created are
benign — the tables become orphaned but unused; an operator who
wants them gone can `DROP TABLE banktransaction;` /
`DROP TABLE economicinvoice;` / `DROP TABLE reconciliationmatch;`.

---

### Phase 2: Danish-CSV parser + import endpoints

**Goal.** Introduce `services/danish_csv.py` (date / amount /
encoding helpers + row validators for Danske-Bank and e-conomic
formats) and the two import endpoints
`POST /bank-transactions/import` and
`POST /economic-invoices/import`. Each is `file_path: str` query
param (`historical_offers.py:44` style, DP-1). Both validate
the company exists, decode UTF-8 → CP-1252 → 422, parse the full
file in memory, validate every row, and write all-or-nothing in
one transaction. Duplicate-import returns 409 from IntegrityError
without partial write. No matching logic, no GET list endpoints
yet — those land in Phase 3.

**Anchors.** `CODE-04` (no existing CSV code — new pattern),
`CODE-06` (router + SessionDep convention),
`CODE-07` (no Danish date / amount parser — must add),
`CONT-04` (POST /bank-transactions/import shape),
`RISK-02` (deduplication via SHA-256 import_hash),
`RISK-03` (integer-øre parse at boundary),
`RISK-06` (Company.get before any write),
`RISK-07` (all-or-nothing validation, 422 with row-level errors),
`RISK-08` (UTF-8 → CP-1252 → 422),
`OPT-C` (single-form import UX — backend ready; UI in Phase 4),
DP-1 (file_path), DP-3 (Danske Bank canonical: DD-MM-YYYY,
semicolon, comma decimal).

**Files.**
```
src/haandvaerker/services/danish_csv.py            (new)
src/haandvaerker/api/bank_transactions.py          (new — import endpoint only)
src/haandvaerker/api/economic_invoices.py          (new — import endpoint only)
src/haandvaerker/main.py                           (edit: register 2 new routers)
tests/test_danish_csv.py                           (new)
tests/test_bank_transactions_import.py             (new)
tests/test_economic_invoices_import.py             (new)
tests/fixtures/danske_bank_sample.csv              (new — 5-row fixture)
tests/fixtures/economic_invoices_sample.csv        (new — 5-row fixture)
tests/fixtures/danske_bank_cp1252.csv              (new — æøå in CP-1252 bytes)
tests/fixtures/danske_bank_malformed.csv           (new — row 3 has bad amount)
```

**Dependencies.** Phase 1 (models exist and are imported via the
new routers).

**Acceptance criteria.**

1. `python -m pytest tests/test_danish_csv.py tests/test_bank_transactions_import.py tests/test_economic_invoices_import.py -v` passes.
2. `python -m pytest tests/ -v` passes the full suite (no regression).
3. `python -c "from haandvaerker.services.danish_csv import parse_danish_amount_ore; assert parse_danish_amount_ore('1.234,56') == 123456 and parse_danish_amount_ore('-1.234,56') == -123456 and parse_danish_amount_ore('0,01') == 1 and parse_danish_amount_ore('12345,67') == 1234567"` exits 0 (`RISK-03`).
4. `python -c "from haandvaerker.services.danish_csv import parse_danish_date; from datetime import date; assert parse_danish_date('14-03-2026') == date(2026, 3, 14)"` exits 0 (DP-3, `CODE-07`).
5. `python -c "from haandvaerker.services.danish_csv import decode_csv_bytes; assert decode_csv_bytes('Dato;Tekst\n14-03-2026;test'.encode('utf-8')).startswith('Dato;Tekst') and decode_csv_bytes('æøå'.encode('cp1252')) == 'æøå'"` exits 0 (`RISK-08`).
6. A test posts `tests/fixtures/danske_bank_sample.csv` (5 rows) twice; first POST returns 201 with `rows_imported=5`; second POST returns 409 (or 201 with `rows_imported=0, rows_skipped=5` — implementer chooses, but the test must assert one of those two and never insert duplicates). After both calls, `SELECT COUNT(*) FROM banktransaction WHERE company_id=?` equals 5 (`RISK-02`).
7. A test posts `tests/fixtures/danske_bank_malformed.csv` (row 3 has `Beloeb` = `abc`); the POST returns 422; the response body's `detail` is a list (not a string) containing an entry mentioning row 3 / line 4; `SELECT COUNT(*) FROM banktransaction WHERE company_id=?` equals 0 (`RISK-07`).
8. A test posts `tests/fixtures/danske_bank_cp1252.csv` and verifies one row's `description` field equals `"Overførsel fra Hansen Byggeri ApS"` (proves CP-1252 fallback, `RISK-08`).
9. A test posts the bank CSV with a `company_id` that does not exist; response is 422 with detail containing `Company` and `not found`; `SELECT COUNT(*) FROM banktransaction` equals 0 (`RISK-06`).
10. `grep -nE "except\s+Exception\s*:" src/haandvaerker/services/danish_csv.py src/haandvaerker/api/bank_transactions.py src/haandvaerker/api/economic_invoices.py` returns no matches in handler-level code (only narrow `UnicodeDecodeError`, `ValueError`, `IntegrityError` allowed — Iron Law 2).
11. `grep -n "from .api.bank_transactions import router" src/haandvaerker/main.py` returns a match and `grep -n "from .api.economic_invoices import router" src/haandvaerker/main.py` returns a match, both with corresponding `app.include_router(...)` calls.
12. `python -c "import inspect; from haandvaerker.api.bank_transactions import import_bank_transactions; sig = inspect.signature(import_bank_transactions); assert 'company_id' in sig.parameters and 'file_path' in sig.parameters and sig.parameters['file_path'].annotation is str"` exits 0 (DP-1).

**Deletions.**

- None. Greenfield phase. Empty by design.

**Subtraction check.** Can this phase be achieved purely by
deletion? No — `csv` module is not used anywhere today
(`CODE-04`); the Danish date / amount / encoding helpers do not
exist (`CODE-07`, `RISK-08`); the two import endpoints do not
exist. Net add ~350 lines (parser ~80, two endpoints ~80 each,
three test files ~180 total, four fixture files ~15 total). The
parser is consolidated into one module so Phase 4 / future
formats don't duplicate it — anti-duplication is the long-run
subtraction.

**Pure-addition flag.** Yes. Justification: greenfield ingest
path. The `danish_csv.py` module is intentionally shared between
the two endpoints so a third (future Nordea / Jyske) parser
extends rather than copies.

**Rollback.** `git revert <sha>` removes
`services/danish_csv.py`, both import endpoints, both routers'
registration in `main.py`, the fixtures, and the tests. Any rows
inserted into `banktransaction` / `economicinvoice` during testing
in a dev DB remain orphaned (no FKs from them point inward); they
can be ignored or `DELETE FROM banktransaction;` / `DELETE FROM
economicinvoice;` cleared.

---

### Phase 3: Reconciliation service + matching / list / action endpoints

**Goal.** Build `services/reconciliation_service.py` (deterministic
exact matcher + AI-supplement matcher behind `local_ai.is_enabled()`)
and the reconciliation router with five endpoints:
`POST /reconciliation/match` (run matching),
`GET /reconciliation/` (combined invoice-centric view),
`POST /reconciliation/manual-match` (accountant links one
transaction to one invoice),
`POST /reconciliation/{match_id}/confirm`,
`POST /reconciliation/{match_id}/reject`. Also add the two list
endpoints `GET /bank-transactions/` and `GET /economic-invoices/`
deferred from Phase 2. Deterministic exact matches land
`confirmed=True`; AI matches land `confirmed=False` and are never
auto-promoted. Manual matches land `confirmed=True` and require
both records to belong to the same company (rejected otherwise).

**Anchors.** `CODE-05` (`chat_completion` signature for AI residual),
`CODE-06` (router + SessionDep convention),
`CODE-09` (fixed-path routes before `/{id}` routes — `manual-match`,
`match` before `{match_id}/confirm`, `{match_id}/reject`),
`CONT-05` (list filter shape: company_id, status, date_from,
date_to, active_only),
`CONT-06` (POST /reconciliation/match shape — proposed vs confirmed),
`CONT-07` (GET /reconciliation/ combined-view shape),
`CONT-08` (confirm / reject state transitions),
`CONT-09` (manual-match validation),
`RISK-03` (integer-øre exact compare in matcher),
`RISK-04` (`confirmed=False` for every `auto_ai` match — Iron Law 3),
`RISK-05` (overdue computed at read time, not stored),
`OPT-B` (deterministic-first + AI supplement).

**Files.**
```
src/haandvaerker/services/reconciliation_service.py    (new)
src/haandvaerker/api/reconciliation.py                 (new — 5 endpoints)
src/haandvaerker/api/bank_transactions.py              (edit: add GET / list)
src/haandvaerker/api/economic_invoices.py              (edit: add GET / list + computed is_overdue)
src/haandvaerker/main.py                               (edit: register reconciliation router)
tests/test_reconciliation_service.py                   (new — pure unit tests of matcher)
tests/test_reconciliation_api.py                       (new — endpoint integration)
tests/test_bank_transactions_list.py                   (new)
tests/test_economic_invoices_list.py                   (new)
```

**Dependencies.** Phase 1 (models), Phase 2 (import endpoints,
`Company` validation pattern, `danish_csv.py` for test fixtures).

**Acceptance criteria.**

1. `python -m pytest tests/test_reconciliation_service.py tests/test_reconciliation_api.py tests/test_bank_transactions_list.py tests/test_economic_invoices_list.py -v` passes.
2. `python -m pytest tests/ -v` passes the full suite (no regression).
3. A unit test in `test_reconciliation_service.py` builds five `BankTransaction` rows and five `EconomicInvoice` rows in-process (no HTTP), calls `run_deterministic_matches(session, company_id)`, and asserts: matches with identical `amount_ore` and `transaction_date` within ±7 days of `invoice_date` are created with `match_type='auto_exact'` and `confirmed=True`; non-matches return no rows; integer comparison is `==`, not `< 0.01` (`RISK-03`, regress against float drift on amounts >= 100,000 DKK).
4. A unit test patches `haandvaerker.services.reconciliation_service.local_ai.is_enabled` to `True` and `local_ai.chat_completion` to return a stub JSON string with a ranked candidate; asserts the resulting match has `match_type='auto_ai'`, `confirmed=False`, `confidence` populated (`RISK-04`, Iron Law 3).
5. A unit test patches `local_ai.is_enabled` to `False`; asserts the AI branch is skipped (no exceptions, deterministic-only result returned).
6. A unit test patches `local_ai.chat_completion` to return `None` (Ollama unavailable mid-run); asserts the matching call still succeeds, returning only deterministic matches (`RISK-04`, fail-loud-but-graceful — `local_ai.py` already logs WARN per `CODE-05`).
7. An API test runs the full happy path: import bank CSV (5 rows), import e-conomic CSV (5 rows matching by amount), POST `/reconciliation/match` with `company_id`, GET `/reconciliation/?company_id=...` returns 5 entries with `match.confirmed=True` and `match.match_type='auto_exact'` for each.
8. An API test calls `POST /reconciliation/manual-match` with a bank_transaction_id and an economic_invoice_id from **different** companies; response is 422 with detail mentioning "company" mismatch; no `ReconciliationMatch` row written (`RISK-06` extended to cross-tenant link).
9. An API test calls `POST /reconciliation/manual-match` for two valid same-company IDs; response is 201; subsequent GET returns the new match with `match_type='manual'`, `confirmed=True`; bank transaction status becomes `matched`; e-conomic invoice status becomes `matched`.
10. An API test confirms an `auto_ai` proposed match: POSTs `/reconciliation/{match_id}/confirm`; asserts the match's `confirmed` flips True, the bank transaction status becomes `matched`, the invoice status becomes `matched`.
11. An API test rejects a confirmed match: POSTs `/reconciliation/{match_id}/reject`; asserts the match's `active` becomes False; bank transaction status reverts to `unmatched`; invoice status reverts to `unmatched`.
12. `python -c "from haandvaerker.api.reconciliation import router; paths = [r.path for r in router.routes]; mm = paths.index('/reconciliation/manual-match'); confirm = next(i for i, p in enumerate(paths) if '/{match_id}/confirm' in p); assert mm < confirm, paths"` exits 0 (`CODE-09`).
13. `python -c "from haandvaerker.api.economic_invoices import _to_read; import inspect; src = inspect.getsource(_to_read); assert 'is_overdue' in src and 'date.today' in src, 'overdue must be computed at read time per RISK-05'"` exits 0.
14. An API test asserts that an unmatched e-conomic invoice with `due_date < today` returns `is_overdue=True` in `GET /economic-invoices/?company_id=...`; the same invoice once matched returns `is_overdue=False` (`RISK-05`, `CONT-05`).
15. `grep -nE "if\s+match\.confirmed\s*=\s*True" src/haandvaerker/services/reconciliation_service.py` returns no matches in the AI branch (manual inspection complement — `RISK-04`: `auto_ai` may never write `confirmed=True` directly).
16. `grep -nE "except\s+Exception\s*:" src/haandvaerker/services/reconciliation_service.py src/haandvaerker/api/reconciliation.py` returns no matches (Iron Law 2).

**Deletions.**

- If Phase 2 left a placeholder `ImportResult`-shaped response or
  a stub handler used only for the import contract: remove it
  now (the implementer notes this in the commit if applicable —
  zero stubs is acceptable). Otherwise empty.

**Subtraction check.** Can this phase be achieved purely by
deletion? No — the matcher and the five reconciliation endpoints
do not exist and cannot be subtracted into being. Net add ~450
lines (matcher service ~120, reconciliation API ~180, list-endpoint
edits ~60, four test files ~280 total). The matcher is the largest
single addition; its size is bounded by Iron Law 3's explicit
"deterministic gate before AI gate" requirement, which is
non-collapsible without losing the invariant.

**Pure-addition flag.** Yes. Justification: greenfield matching
service for a new capability; no existing matcher to remove.

**Rollback.** `git revert <sha>` removes the matcher service,
the reconciliation router, the list-endpoint additions in the
two import routers, and the router registration. Any
`reconciliationmatch` rows written during testing in a dev DB
remain orphaned and can be ignored or
`DELETE FROM reconciliationmatch;` cleared. Bank-transaction and
economic-invoice status columns may have been mutated from
`unmatched` to `matched`; an operator can `UPDATE banktransaction
SET status='unmatched' WHERE company_id=?;` if needed.

---

### Phase 4: Frontend reconciliation page + Overblik dashboard tiles

**Goal.** Add `reconciliation.html` static page following the
`export.html` toolbar / table / badge primitive (`OPT-D`) and a
matching `/reconciliation` HTML route in `main.py`. Add three
additive fields to `DashboardRead`
(`reconciliation_unmatched_invoices`, `reconciliation_overdue_invoices`,
`reconciliation_overdue_amount_ore`) and populate them in
`api/dashboard.py:get_dashboard` with three count / sum queries
scoped by `company_id` (`OPT-F`). The page renders an
invoice-centric table (one row per `EconomicInvoice` with badges
for status / overdue), a secondary "orphan transactions" section
below (bank transactions with no match), a single-form import
toolbar (file_path text input + `Bankudtog` / `e-conomic
faktura-eksport` dropdown — `OPT-C`), and a "Kør afstemning"
button that POSTs `/reconciliation/match` (DP-5). The dashboard
KPI tile change in this phase is **backend only** — `DashboardRead`
gets the three new fields; the Overblik HTML tile rendering is in
the same `ui.html` if the existing stat-grid pattern accommodates
it without restructuring (it does per `OPT-F` evidence). Test
updates for `test_dashboard.py` are deferred to Phase 5.

**Anchors.** `CODE-09` (fixed-path routes — landing route
`/reconciliation` is HTML, must not collide with the API prefix —
the API uses prefix `/reconciliation` so the HTML landing route
in `main.py` uses a different path; brief calls for
`/reconciliation/ui` analogue per existing `/ui`, `/export`),
`IMPACT-03` (DashboardRead additive fields; assertion list
update is in Phase 5),
`RISK-01` (CSV-injection defense for description rendering:
escape as text nodes, never `innerHTML`),
`RISK-05` (overdue rendered from API's `is_overdue` field, never
recomputed in JS from raw date),
`OPT-C` (single drop / form + type dropdown — toolbar select
pattern from `export.html:21`),
`OPT-D` (invoice-centric table + orphan-transactions secondary),
`OPT-F` (badges + dashboard tiles),
DP-4 (dashboard in v1),
DP-5 (manual "Kør afstemning" trigger).

**Files.**
```
src/haandvaerker/static/reconciliation.html        (new)
src/haandvaerker/static/ui.html                    (edit: 3 stat tiles)
src/haandvaerker/main.py                           (edit: 1 HTML route)
src/haandvaerker/models/dashboard.py               (edit: 3 fields)
src/haandvaerker/api/dashboard.py                  (edit: 3 queries)
```

**Dependencies.** Phase 3 (the page calls
`GET /reconciliation/`, `POST /reconciliation/match`,
`POST /reconciliation/manual-match`,
`POST /reconciliation/{match_id}/confirm`,
`POST /reconciliation/{match_id}/reject`,
`POST /bank-transactions/import`,
`POST /economic-invoices/import`,
`GET /bank-transactions/`, `GET /economic-invoices/`).

**Acceptance criteria.**

1. `python -m pytest tests/ -v` passes the full suite (test_dashboard.py will be updated in Phase 5; for Phase 4 it must still pass because the existing assertion uses `assert field in data`, not equality, so additive fields don't break it — verify this by running the suite at end-of-phase).
2. `python -c "from haandvaerker.models.dashboard import DashboardRead; fields = DashboardRead.model_fields.keys(); assert 'reconciliation_unmatched_invoices' in fields and 'reconciliation_overdue_invoices' in fields and 'reconciliation_overdue_amount_ore' in fields"` exits 0.
3. A manual `curl http://localhost:8000/reconciliation` (or equivalent) returns 200 HTML with `<title>` containing "Bankafstemning" or "Afstemning". Documented in commit message; not gated by CI.
4. `grep -n "reconciliation.html" src/haandvaerker/main.py` returns a match registering the HTML route (`@app.get("/reconciliation"` or `/afstemning`).
5. `grep -nE "innerHTML\s*=" src/haandvaerker/static/reconciliation.html` returns no matches (`RISK-01`: render description as text node, never HTML — use `.textContent =`).
6. `grep -n "textContent" src/haandvaerker/static/reconciliation.html` returns at least one match (proves the escape discipline is applied where description is rendered).
7. `grep -nE "(is_overdue|isOverdue)" src/haandvaerker/static/reconciliation.html` returns matches that read the API field rather than computing it in JS (`RISK-05`).
8. `grep -n "Kør afstemning" src/haandvaerker/static/reconciliation.html` returns a match (DP-5 button label).
9. `grep -n "POST" src/haandvaerker/static/reconciliation.html | grep -i "/reconciliation/match"` returns a match (the button POSTs the correct endpoint).
10. `grep -n "select" src/haandvaerker/static/reconciliation.html | grep -iE "Bankudtog|e-conomic"` returns a match (`OPT-C`: type dropdown).
11. `grep -n "b-needs_review\|b-paid\|b-pending" src/haandvaerker/static/reconciliation.html` returns matches reusing the existing badge CSS classes (`OPT-D`, `OPT-F`).
12. `grep -n "reconciliation_unmatched_invoices" src/haandvaerker/static/ui.html` returns a match (the stat tile is wired in).
13. Manual: with bank + e-conomic CSVs imported and matching run, the page shows one row per `EconomicInvoice` with status badge, and a secondary section listing unmatched bank transactions. The dashboard tile shows the correct count. Documented in commit message; not gated.

**Deletions.**

- None in production code. The existing `export.html`,
  `ui.html`, `index.html`, etc. are not modified beyond the
  one stat-tile addition in `ui.html`. Empty by design for
  this phase.

**Subtraction check.** Can this phase be achieved purely by
deletion? No — the static page does not exist and the
DashboardRead fields are net-new. The single avoidance of
addition is: we do not create a second HTML page for the import
form (`OPT-C` puts both on one page); we do not create a
separate dashboard partial (the existing `stat-grid` pattern
absorbs the new tiles).

**Pure-addition flag.** Yes. Justification: new frontend
surface for a new capability. The single `ui.html` edit is
additive (one new stat tile in the existing `stat-grid`).

**Rollback.** `git revert <sha>` removes
`static/reconciliation.html`, the HTML route line in `main.py`,
the three fields from `DashboardRead`, the three queries from
`api/dashboard.py:get_dashboard`, and the stat-tile snippet in
`ui.html`. No DB change. Note: if Phase 5's `test_dashboard.py`
update has landed, that test will start failing after this
phase's revert — coordinate revert order
(Phase 5 revert before Phase 4 revert).

---

### Phase 5: Test coverage completion — dashboard fields + cross-phase integration

**Goal.** Update `tests/test_dashboard.py:34-40` to assert on the
three new reconciliation fields, add three new dashboard tests
covering the count / sum queries, and add a cross-phase
integration test that imports both CSVs, runs matching, confirms
an AI-proposed match, rejects another, and verifies all four
endpoints' state is consistent end-to-end.

**Anchors.** `IMPACT-03` (test_dashboard.py field-list
assertion must be updated when DashboardRead grows),
`CONT-10` (test pattern: helper functions, TestClient, in-memory
SQLite, `_setup`-style helpers).

**Files.**
```
tests/test_dashboard.py                              (edit: extend assertion + 3 tests)
tests/test_reconciliation_integration.py             (new)
```

**Dependencies.** Phases 1–4.

**Acceptance criteria.**

1. `python -m pytest tests/test_dashboard.py -v` passes all
   existing tests plus three new tests:
   `test_dashboard_reconciliation_unmatched_count`,
   `test_dashboard_reconciliation_overdue_count`,
   `test_dashboard_reconciliation_overdue_amount` — each asserts
   the relevant new field is populated correctly after importing
   sample CSV data.
2. `python -m pytest tests/test_reconciliation_integration.py -v`
   passes one end-to-end test: import 3-row bank CSV, import 3-row
   e-conomic CSV (one with mismatched amount), POST `/reconciliation/match`,
   GET `/reconciliation/` returns 2 auto-confirmed matches + 1
   orphan invoice + 1 orphan transaction, then POST `/reconciliation/manual-match`
   the orphan pair, then POST `/reconciliation/{id}/reject` one of
   the auto-confirmed matches, then verify
   `GET /economic-invoices/?company_id=...` and
   `GET /bank-transactions/?company_id=...` show the expected
   `status` values and `is_overdue` flags.
3. `python -m pytest tests/ -v` passes the full suite with zero
   regressions in any of the existing 230+ tests.
4. `python -c "import re, pathlib; src = pathlib.Path('tests/test_dashboard.py').read_text(encoding='utf-8'); assert 'reconciliation_unmatched_invoices' in src and 'reconciliation_overdue_invoices' in src and 'reconciliation_overdue_amount_ore' in src, 'test_dashboard.py field list must be extended'"` exits 0 (`IMPACT-03`).
5. The new integration test uses the `client` and `company_id`
   fixtures from `tests/conftest.py` unchanged (no conftest
   edit) — `grep -n "from tests.conftest" tests/test_reconciliation_integration.py` returns no match (proves the test relies only on pytest fixture autodiscovery, matching `CONT-10`).

**Deletions.**

- The implementer may delete any obsolete `# TODO`,
  `# placeholder`, or commented-out test stub left by an
  earlier phase. If none exist, this is empty.

**Subtraction check.** Can this phase be achieved purely by
deletion? Partially — extending the assertion list in
`test_dashboard.py:34-40` could in theory be skipped if the
fields were already in the assertion list, but they are not.
Adding three count tests and one integration test is irreducible
to deletion. Net add ~120 lines (three short dashboard tests
~10 lines each, one integration test ~80 lines, assertion list
extension ~3 lines).

**Pure-addition flag.** Yes, by design. Justification: this is
the test-completion phase; tests are intentionally additive.

**Rollback.** `git revert <sha>` removes the new tests and
restores the `test_dashboard.py` assertion list. If Phases 1–4
remain, the test_dashboard.py assertion will still pass (it uses
`assert field in data` semantics; the three new fields on
DashboardRead are present but un-asserted). No DB change.

---

## Cross-cutting concerns

- **company_id isolation (`CODE-08`, `RISK-06`).** Every list and
  import endpoint requires `company_id`. Every import endpoint
  calls `session.get(Company, company_id)` and raises 422 with
  `f"Company '{company_id}' not found"` (matches
  `api/dashboard.py:28-29` for consistency) before any row write.
  The `manual-match` endpoint re-reads both
  `BankTransaction.company_id` and
  `EconomicInvoice.company_id` and rejects if they differ.
- **Amount precision (`RISK-03`).** Every new model field for
  money is `int` (øre). Conversion happens at the CSV boundary
  in `services/danish_csv.py`. The matcher uses integer `==`.
  The dashboard sum query returns integer øre; the frontend
  divides by 100 for display.
- **Iron Law 2 — fail loud (`RISK-02`, `RISK-07`, `RISK-08`).**
  No `except Exception:` in any new file. Only narrow catches:
  `UnicodeDecodeError` (encoding fallback), `ValueError`
  (Danish-format parse), `sqlalchemy.exc.IntegrityError`
  (duplicate-import → 409), `json.JSONDecodeError` (AI response
  parse). Each catch logs at WARNING with context and either
  raises HTTPException 422/409 or returns a typed empty result
  the caller handles explicitly.
- **Iron Law 3 — code decides (`RISK-04`, `OPT-B`).** AI
  `chat_completion` is called only inside
  `services/reconciliation_service.py`'s residual-matcher branch,
  always behind `local_ai.is_enabled()`. AI matches write
  `confirmed=False`. Promotion to `confirmed=True` for `auto_ai`
  requires `POST /reconciliation/{match_id}/confirm` from a
  human caller. Deterministic exact matches
  (`match_type='auto_exact'`) and manual matches
  (`match_type='manual'`) write `confirmed=True` directly.
- **No external network (sandbox).** AI calls go to
  `settings.local_ai_endpoint` (localhost only — `local_ai.py:5`
  docstring). CSV ingest is from local filesystem only
  (`file_path: str` per DP-1). No e-conomic or bank API client
  is added.
- **CSV injection / XSS (`RISK-01`).** The reconciliation HTML
  page renders all description / customer-name strings via
  `.textContent =` (never `.innerHTML =`); a grep gate enforces
  it (Phase 4 AC-5/AC-6). Existing `export_data.py` XLSX export
  is not extended to reconciliation in v1, so the
  spreadsheet-formula-injection surface is not opened.
- **Soft delete (`CODE-02`).** All three new models carry
  `active: bool`. The reject endpoint flips
  `ReconciliationMatch.active = False`. List endpoints accept
  `active_only: bool = True` default.
- **Routing order (`CODE-09`).** In `api/reconciliation.py`,
  fixed-path routes (`/manual-match`, `/match`) are registered
  before `/{match_id}/confirm` and `/{match_id}/reject`.
  A test asserts the order at the router-registration level
  (Phase 3 AC-12).
- **Tests stay green (`IMPACT-04`).** No required new column
  without a default. The conftest fixture is unchanged. Phase 5
  updates `test_dashboard.py` in place rather than rewriting it,
  preserving the 21 existing dashboard tests.

---

## Out of scope

- **Auth / authorisation layer.** `company_id` is caller-supplied
  and validated only by DB existence (`RISK-06` is mitigated to
  the extent the brief allows — full RBAC is the existing
  codebase gap, not introduced here).
- **`haandvaerker.Invoice` ↔ `EconomicInvoice` linking
  (`IMPACT-02`).** The brief's Resolved Questions say
  reconciliation does NOT update `Invoice.status`. Adding a FK
  from `EconomicInvoice` to `Invoice` is a separate plan.
- **`EconomicInvoice.linked_project_id` population.**
  The nullable column exists (Phase 1, `OPT-E`) but the
  "Link til projekt" inline-dropdown UI and the
  `POST /economic-invoices/{id}/link-project` endpoint are
  deferred to a follow-up plan.
- **Reconciliation XLSX / CSV export
  (`IMPACT-05`).** `api/export_data.py` is not extended to a
  reconciliation handler in v1. The reconciliation page has
  print-to-PDF via the browser, matching `export.html`'s
  `@media print` pattern.
- **Second / third bank format
  (Nordea, Jyske).** The parser is structured to accept a
  `bank_format` switch later (`CONT-04`), but only the
  `danske_bank` branch is implemented and tested in v1 (DP-3).
- **Split payment in the matcher.** The data model supports
  many-to-many (DP-2), but the deterministic matcher only
  proposes 1-bank-to-1-invoice matches in v1. Split-payment
  resolution is manual: the accountant uses `manual-match`
  twice for the same bank transaction. A "propose split" matcher
  is a follow-up.
- **Partial-amount tolerance in the deterministic matcher.**
  Exact `amount_ore ==` only in v1. Bank fees / rounding
  differences cause non-matches that fall through to AI
  residual or accountant action.
- **Background / async matching.** The
  `POST /reconciliation/match` endpoint runs synchronously
  (matches the demo / single-user context; AI latency is
  bounded to residual; no FastAPI `BackgroundTasks` machinery
  introduced).
- **`is_urgent` / customer-name fuzzy auto-link
  (`OPT-4C`).** Not introduced; deferred to a future plan if
  the accountant requests it after using v1.
- **External API calls to e-conomic or banks.** Sandbox
  constraint. CSV-only ingest. No client library added.
- **Migration framework (Alembic).** `AGENTS.md §"Adding a new
  resource"` lists "write an alembic revision" as step 4, but
  `alembic/` does not exist in this repository (verified: Glob
  `alembic/**/*` returns empty) and `database.py:8-9` is the
  live code path — `SQLModel.metadata.create_all(engine)`
  creates all tables on startup. Alembic was never set up.
  The new tables are picked up automatically by both
  `create_db_and_tables()` and `conftest.py:17`'s matching
  `create_all` call (`IMPACT-04`). No Alembic step in this plan.
  If a future plan introduces Alembic, it should also migrate the
  three tables added here.
- **CSV injection sanitisation of `=` / `+` / `-` / `@` prefixes
  in description fields (`RISK-01`).** Only the XSS leg is
  mitigated in v1 (HTML text nodes). The spreadsheet-formula
  leg is not opened because reconciliation export is not in
  scope. If reconciliation export is added later, the
  sanitisation gate must be added at the export boundary.
- **Re-running matching on already-matched transactions.**
  `POST /reconciliation/match` skips rows whose status is
  already `matched`. Re-matching requires the accountant to
  reject the existing match first.

## Open questions for the user

None — all five `DP-*` decisions were resolved by the user
before plan writing (see brief.md §"User-Resolved Design
Decisions"). The plan is complete as-is.

## Review invocation

After phase 5 verifies PASS, invoke the `review` skill on
`git diff main...HEAD`. The review skill picks its own reviewer
count and concerns.
