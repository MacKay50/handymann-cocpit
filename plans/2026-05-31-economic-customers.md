# Plan: E-conomic customers — import, CVR sync, address history, repeat-job

**Path:** plans/2026-05-31-economic-customers.md
**Created:** 2026-05-31
**Research:** research/2026-05-31-economic-customers/
**Status:** draft

## Research anchors

All artifacts live under `research/2026-05-31-economic-customers/`
(gitignored — regenerate via `develop-conductor` if missing):

- `meta.json` — slug, three researchers, status `synthesised`,
  decisions recorded.
- `brief.md` — synthesised summary, full decision log (D1–D6),
  risk highlights and proposed phase structure.
- `R1-models-migration.json` — model field signatures, enum/UUID/FK
  patterns, schema-side risks, `CONTRACT-01/02` on `create_all()`
  limitation, `CODE-11` on `models/__init__.py` discovery
  requirement.
- `R2-csv-parser-import.json` — `decode_csv_bytes` cascade,
  `parse_economic_invoice_csv` as direct template, `CODE-07`
  UploadFile parameter ordering, `CODE-09` business-key dedup
  pattern, `CODE-10` missing fixture, `IMPACT-06` registry
  wiring.
- `R3-endpoints-flows.json` — `CONTRACT-01/02` Customer create
  contract, `CONTRACT-03/04` Project/Quote create contracts,
  `CONTRACT-10/12` route-ordering rules, `RISK-01/02` CVR
  ambiguity and idempotency, `RISK-06` repeat-job atomicity,
  `RISK-07` schema-add migration risk.

Phases below cite specific finding IDs (e.g. `R1.CODE-09`,
`R2.IMPACT-02`, `R3.RISK-06`) where each decision is anchored.

## Problem

The codebase has no way to ingest the e-conomic customer master
list, link those records to the existing `Customer` CRM rows by
CVR, look up prior work at an address across both `Project` and
`HistoricalOffer` history, or rebook a returning customer with a
single click. Today, none of the four capabilities exists: there
is no `EconomicCustomer` table at all, `HistoricalOffer` has no
`address` field, and creating a repeat project + draft quote
requires two separate API calls with a race window between them
(R3.RISK-06). This plan delivers all four capabilities in three
phases, deferring Alembic adoption (D1=B — demo reset only) and
relying on `reset_demo.bat` dropping `haandvaerker.db` before
each schema-change test cycle.

## Approach

Three sequential phases, each commit-worthy, each scoped to a
single architectural concern:

1. **Greenfield ingest slice** — new `EconomicCustomer` table,
   new CSV parser, new import + list endpoints. Direct mirror of
   the established `EconomicInvoice` pipeline (R2.IMPACT-01/02);
   no incumbent pattern is touched, only extended sideways.
2. **Schema additions + link/sync surface** — two column
   additions (`Customer.economic_customer_number`,
   `HistoricalOffer.address`), two sync endpoints, one
   address-history endpoint. Implements the CVR-lookup-or-create
   idempotency guard (R3.RISK-02) and the case-insensitive
   substring strategy (D4).
3. **Atomic repeat-job + test coverage** — single endpoint that
   creates Project + Quote in one session/transaction
   (R3.RISK-06), plus a single test file per new endpoint family
   so the demo is verifiable.

Cross-cutting decisions baked in (do NOT re-open): D1=B (no
Alembic, comment in `database.py`), D2 (no UNIQUE on
`cvr_number`, first-active wins), D3 (already-linked → 200 with
existing), D4 (case-insensitive LIKE `%query%`, address as query
param), D5 (caller supplies `title` and optional `address`), D6
(`economic_customer_number` added directly to `CustomerRead` +
`from_orm_masked()`).

## Architectural posture

This plan **extends three incumbent patterns** rather than
redesigning any:

1. **The imported-data pipeline pattern** (`bank_transactions`,
   `economic_invoices`). The new `EconomicCustomer` resource is
   the third instance of: SQLModel table with `(company_id,
   business_key)` compound unique index → `parse_*_csv` in
   `danish_csv.py` → twin `/import` + `/import-upload`
   endpoints → `IntegrityError → 409` batch-atomic commit. The
   options researcher did not surface a redesign option because
   the pattern has two clean prior instances — extending to a
   third is straightforward and *reduces* per-resource variance.
2. **The "router file per resource" pattern**
   (`src/haandvaerker/api/<resource>.py` plus registration in
   `main.py`). New file `api/economic_customers.py` follows the
   same shape as `api/economic_invoices.py`. The two endpoint
   additions to `api/customers.py` (address-history, repeat-job)
   follow the existing helpers `_require_active_company` /
   `_require_active_customer` convention.
3. **The masked-read schema pattern** (`CustomerRead` /
   `from_orm_masked()`). D6 adds `economic_customer_number`
   directly to `CustomerRead` because it is not sensitive — this
   *extends without weakening* the masking discipline for the
   genuinely sensitive `cvr_number` field, which remains masked.

**Architectural fit on the four dimensions:**

- **Separation.** Concerns stay where they belong: parsers in
  `services/danish_csv.py`, routes in `api/*.py`, schemas in
  `models/*.py`. The `EconomicCustomer` table is deliberately a
  *separate* table from `Customer` (R2.IMPACT-05) — imported
  master data is not conflated with hand-crafted CRM data; the
  link is one explicit FK (`linked_customer_id`).
- **Pick-up-ability.** A new engineer finds the new ingest slice
  by the established prefix-and-mirror convention — if they
  understand `economic_invoices`, they understand
  `economic_customers` in under 10 minutes.
- **Extensibility.** The next related changes (a sync-history
  table, an EconomicCustomer update endpoint, an
  `economic_invoice.customer_id` FK rollup) all become easier
  because the canonical link column `linked_customer_id` now
  exists. Repeat-job's atomic-transaction shape is the template
  for any future "compose two resources in one call" endpoint.
- **Security / stability.** No trust boundary is widened.
  `cvr_number` masking remains intact (D6 only exposes the
  non-sensitive `economic_customer_number`). The `repeat-job`
  endpoint *narrows* an existing risk (R3.RISK-06 orphaned
  Project) by collapsing two HTTP calls into one transaction.
  The CVR-multi-match risk (R3.RISK-01) is explicitly bounded by
  D2's first-active-wins rule and documented in code.

**Debt accrued by extension:**

- **No Alembic bootstrapping (D1=B).** This is the largest piece
  of accrued debt. The plan documents the limitation in
  `database.py` and depends on `reset_demo.bat` always dropping
  the DB. **Pay-down trigger:** the next column addition on an
  existing table that cannot tolerate a demo reset (e.g. any
  change touching production-shaped data) MUST be preceded by a
  separate Alembic-bootstrap plan. The comment in `database.py`
  serves as the in-code reminder.
- **No UNIQUE on `Customer.cvr_number` (D2).** Multi-CVR
  customers are possible. Documented inline at the sync site.
  **Pay-down trigger:** when a deduplication pass on `Customer`
  is scheduled, that plan adds the unique constraint and merges
  the duplicates.
- **`_next_quote_number()` consumes a number per empty shell
  quote (R3.RISK-05).** Acceptable for the demo; flagged in the
  out-of-scope section.

## Invariants preserved

- **`vision.md` §6 / AGENTS.md key rule 4**: `cvr_number` remains
  masked in every `CustomerRead` response (`cvr_masked` only).
  D6 only adds the non-sensitive `economic_customer_number`.
- **AGENTS.md key rule 2 / Iron Law 2 (fail loud)**: every new
  endpoint raises explicit `HTTPException` with status + detail
  on error; no silent defaults. Missing customer → 404. Inactive
  customer → 422. Duplicate-key import → 409. Missing required
  field in CSV → 422 with full error list.
- **AGENTS.md key rule 6 (UUID-idempotens)**: every new table PK
  is `str = Field(default_factory=lambda: str(uuid.uuid4()),
  primary_key=True)`. Sync endpoint is idempotent by
  CVR-lookup-or-create (D3).
- **AGENTS.md key rule 7 (no ORM in responses)**: every new
  endpoint returns a Pydantic schema (`EconomicCustomerRead`,
  `CustomerRead`, `ProjectRead`, `QuoteRead`,
  `ImportResult`) — never a raw SQLModel.
- **AGENTS.md "Adding a new resource" steps 1–3, 5**: model →
  router → main.py registration → tests. Step 4 (Alembic) is
  explicitly waived per D1=B.
- **Iron Law 1 (ask on ambiguity)**: D1–D6 were all resolved by
  the user in the research brief; no silent choices remain in
  this plan.

## Phases

### Phase 1: EconomicCustomer ingest slice

**Goal.** Land the new `EconomicCustomer` table, CSV parser,
import + list endpoints, fixture, and wiring — a complete
greenfield slice with zero edits to existing tables.

**Anchors.** `R1.CODE-07/08/09` (enum/UUID/FK patterns),
`R1.CODE-11` (`models/__init__.py` registry), `R1.CONTRACT-05/06`
(EconomicInvoice compound unique index + `imported_at`/`active`
pattern), `R2.CODE-01` (`decode_csv_bytes`), `R2.CODE-03/04`
(`ImportResult` + all-or-nothing), `R2.CODE-07` (UploadFile
parameter order), `R2.CODE-09` (business-key dedup),
`R2.CODE-10` (missing fixture), `R2.IMPACT-01/02` (template),
`R2.IMPACT-05` (separate table), `R2.IMPACT-06` (registry
wiring), `R3.RISK-10` (router registration), `R3.CONTRACT-10`
(`sync-all` fixed-before-parameterised — relevant for the
sync routes added in Phase 2 but the router file is created
here; document the ordering invariant in a comment).

**Files.**
```
src/haandvaerker/models/economic_customer.py          (new)
src/haandvaerker/models/__init__.py                   (edit — export)
src/haandvaerker/services/danish_csv.py               (edit — add parser)
src/haandvaerker/api/economic_customers.py            (new)
src/haandvaerker/main.py                              (edit — include_router)
src/haandvaerker/database.py                          (edit — D1=B comment)
tests/fixtures/economic_customers_sample.csv          (new)
```

These are the ONLY paths the implementer may touch in Phase 1.

**Dependencies.** None.

**Acceptance criteria.**

1. `pytest tests/ -x` passes (no tests deleted, no regression in
   existing test files).
2. `python -c "from haandvaerker.models import EconomicCustomer,
   EconomicCustomerCreate, EconomicCustomerRead; print('ok')"`
   prints `ok` (registry export wired per R1.CODE-11 /
   R2.IMPACT-06).
3. `python -c "from haandvaerker.main import app;
   print([r.path for r in app.routes if
   '/economic-customers' in r.path])"` prints exactly four
   routes: `/economic-customers/import`,
   `/economic-customers/import-upload`, `/economic-customers/`,
   and at most the FastAPI auto-generated trailing-slash
   variants. (Sync routes are added in Phase 2.)
4. `ruff check --select E711,E722,F841,F401,B006,B007,S106,RUF100
   src/haandvaerker/models/economic_customer.py
   src/haandvaerker/api/economic_customers.py
   src/haandvaerker/services/danish_csv.py` returns zero
   findings.
5. `grep -c "economic_customer_number" src/haandvaerker/models/economic_customer.py`
   returns at least 2 (the column declaration and the compound
   index).
6. The compound unique index on
   `(company_id, economic_customer_number)` exists — verified by
   `grep "ix_economiccustomer_company_number"
   src/haandvaerker/models/economic_customer.py` returning 1.
7. `grep "demo reset" src/haandvaerker/database.py` returns at
   least 1 line (D1=B comment landed).
8. Fixture file `tests/fixtures/economic_customers_sample.csv`
   exists with header
   `Kundenummer;Navn;Adresse;Postnummer;By;CVR;Email;Telefon`
   and at least 3 data rows (mix of CVR present / absent /
   needs-stripping).

**Deletions.** None for this phase. This is a pure greenfield
ingest slice — no prior `EconomicCustomer` code exists to
replace (R1.CODE-10 confirms grep returned zero hits across
src/). The subtraction check below explains why no deletion is
available.

**Subtraction check.** Can this phase be achieved purely by
deletion? **No.** R1.CODE-10 confirms the EconomicCustomer
concept does not exist anywhere in the codebase. There is
nothing to delete; the capability has to be built. The
mitigation against pure-additive growth is that this phase
deliberately *reuses* `decode_csv_bytes`, `ImportResult`, the
`SessionDep` alias, and the EconomicInvoice endpoint shape
verbatim — no parallel implementation is introduced.

**Net LoC intent.** ~250 net additions (model ~80, parser ~50,
router ~80, fixture ~5, wiring ~5, `database.py` comment ~3).
Flagged as the largest phase but justified by the
greenfield-slice scope and the fact that ~70% mirrors existing
files line-for-line.

**Rollback.** `git revert` the phase commit; no schema migration
to undo because `create_all()` only creates tables. On next
boot, `create_all()` will simply not create the `economiccustomer`
table (no error). For local databases that already received the
table: drop via `reset_demo.bat` (D1=B contract).

---

### Phase 2: Customer + HistoricalOffer schema, sync + address-history

**Goal.** Add the two column additions
(`Customer.economic_customer_number`,
`HistoricalOffer.address`), wire them into Read/Update schemas,
and land the three new endpoints that depend on them:
single-sync, sync-all, address-history.

**Anchors.** `R1.CODE-02` (`from_orm_masked` factory),
`R1.CODE-05` (HistoricalOffer table + Read + Update all lack
`address`), `R1.CODE-06` (Project.address reference type),
`R1.CONTRACT-04` (CustomerRead manual composition),
`R1.CONTRACT-08` (HistoricalOfferRead/Update must be updated
atomically), `R2.CODE-08` (CVR normalization precedent — none
exists; parser owns it from Phase 1), `R3.CONTRACT-01/02`
(Customer create contract for sync), `R3.CONTRACT-06`
(404 vs 422 error pattern), `R3.CONTRACT-09` (no existing
address-indexed query), `R3.CONTRACT-10` (`sync-all` before
`/{id}/sync` registration order — HARD), `R3.CONTRACT-12`
(fixed sub-paths before parameterised on customers router),
`R3.RISK-01` (no UNIQUE on cvr_number — D2 first-active wins),
`R3.RISK-02` (sync-all idempotency guard via CVR-lookup-or-create
— D3 already-linked → 200), `R3.RISK-03` (cvr_masked is the
audit signal in the response), `R3.RISK-04` (inactive customer
handling — address-history may return empty; sync may target an
already-linked customer that became inactive — return 200 with
existing), `R3.RISK-07` (schema-add migration risk — mitigated
by D1=B / reset), `R3.RISK-09` (blank-name `EconomicCustomer`
fails `CustomerCreate.name min_length=1` — resolved by the
batch-skip / single-422 asymmetry documented under cross-cutting
"Sync failure mode for invalid EconomicCustomer records"; this
phase MUST implement that response shape, including the
`warnings: list[str]` field).

**Files.**
```
src/haandvaerker/models/customer.py                   (edit — column + schemas)
src/haandvaerker/models/historical_offer.py           (edit — column + schemas)
src/haandvaerker/api/economic_customers.py            (edit — sync routes)
src/haandvaerker/api/customers.py                     (edit — address-history)
tests/test_economic_customers_sync.py                 (new — sync integration test, see AC 8)
```

These are the ONLY paths the implementer may touch in Phase 2.

**Dependencies.** Phase 1 (the `EconomicCustomer` table and
router file must exist).

**Acceptance criteria.**

1. `pytest tests/ -x` passes.
2. `grep "economic_customer_number"
   src/haandvaerker/models/customer.py` returns at least 4
   hits: column on `Customer`, `CustomerCreate`,
   `CustomerUpdate`, `CustomerRead` (D6).
3. `grep "economic_customer_number"
   src/haandvaerker/models/customer.py` shows
   `from_orm_masked` updated (line that assigns
   `economic_customer_number=` inside the factory).
4. `grep "address" src/haandvaerker/models/historical_offer.py`
   returns hits in the table model, `HistoricalOfferRead`, and
   `HistoricalOfferUpdate` (R1.CONTRACT-08 — all three updated
   atomically).
5. `python -c "from haandvaerker.main import app; paths = [r.path
   for r in app.routes]; assert
   '/economic-customers/sync-all' in paths; assert
   '/economic-customers/{economic_customer_id}/sync' in paths or
   '/economic-customers/{id}/sync' in paths; print('ok')"`
   prints `ok`.
6. Route ordering verified: in
   `src/haandvaerker/api/economic_customers.py`, the line
   defining the `sync-all` route appears before the line
   defining the `/{id}/sync` route — verified by
   `awk '/sync-all/{a=NR} /\{.*\}\/sync/{b=NR} END{exit a<b?0:1}'
   src/haandvaerker/api/economic_customers.py` exits 0
   (R3.CONTRACT-10).
7. `grep "address-history"
   src/haandvaerker/api/customers.py` returns at least 1 line.
8. Add a minimal integration test to a new file
   `tests/test_economic_customers_sync.py` that:
   - Imports 2 `EconomicCustomer` records (one with CVR matching
     an existing `Customer`, one without any matching `Customer`).
   - Calls `POST /economic-customers/sync-all?company_id=...`.
   - Asserts the response equals
     `{"matched": 1, "created": 1, "skipped": 0, "warnings": []}`
     (the `warnings` key MUST be present even when empty — see
     cross-cutting "Sync failure mode" below).
   - Asserts the created `Customer` has
     `economic_customer_number` populated.
   This test file is **created in Phase 2** with the sync
   integration test only. Phase 3 expands this file with
   additional cases (already-linked → 200, sync-all with mixed
   matched/created/skipped + warnings, blank-name skip, etc. —
   see Phase 3 acceptance criterion 1). The verifiable gate for
   Phase 2 is: `pytest tests/test_economic_customers_sync.py -x`
   exits 0.
9. `ruff check --select E711,E722,F841,F401,B006,B007,S106,RUF100
   src/haandvaerker/models/customer.py
   src/haandvaerker/models/historical_offer.py
   src/haandvaerker/api/economic_customers.py
   src/haandvaerker/api/customers.py` returns zero findings.
10. The CVR-lookup-or-create logic uses
    `WHERE cvr_number = ? AND active = TRUE` and takes the first
    result (D2 + R3.RISK-01) — verified by code reading; the
    inline comment near the query references `D2`.

**Deletions.** None expected. If a now-obsolete TODO comment or
stub appears around the customer model during column addition,
remove it as part of this phase and list it here. The plan
explicitly accepts an empty deletions block in this phase
because both column additions are pure capability extensions,
but the implementer must surface and delete any incidental dead
code uncovered.

**Subtraction check.** Can this phase be achieved purely by
deletion? **No.** The schema-add concern is irreducibly
additive (two columns, three endpoints). Mitigation against
additive sprawl: the sync logic is two endpoints sharing one
private helper `_sync_one(...)` so single-sync and sync-all do
not duplicate the CVR-lookup-or-create branch. The
address-history endpoint reuses existing query helpers and adds
no new service-layer module.

**Net LoC intent.** ~220 net additions (model edits ~30, sync
endpoints + helper ~80, address-history endpoint ~40, schema
edits ~30, sync integration test ~40). Below the 100-line
soft-flag threshold per file. The narrow exception to
"Phase 2 adds no tests" rule (see cross-cutting "Tests") is the
single sync integration test that AC 8 requires — this replaces
the prior manual-smoke AC with a mechanically verifiable one.

**Rollback.** `git revert` the phase commit. Because `create_all()`
is a no-op for column additions on existing tables, the columns
will not be silently retained; the rollback contract is
"reset_demo.bat → start fresh DB → schema reverts with the
code". Document this in the commit message.

---

### Phase 3: repeat-job atomic endpoint + endpoint test coverage

**Goal.** Land the single atomic `POST
/customers/{customer_id}/repeat-job` endpoint that creates
Project + Quote in one session transaction, then add the
test files covering all endpoints introduced in Phases 1–3.

**Anchors.** `R3.CONTRACT-03` (`ProjectCreate` needs `title` +
`customer_id`; company_id derived), `R3.CONTRACT-04`
(`QuoteCreate` accepts `lines=[]`), `R3.CONTRACT-05`
(QuoteLine contract for future, not needed here),
`R3.CONTRACT-12` (sub-paths on customers router safe but
declare order for clarity), `R3.RISK-04` (inactive customer →
422), `R3.RISK-05` (empty-shell quote consumes a sequence
number — accepted for demo, no mitigation in scope),
`R3.RISK-06` (one transaction, not two HTTP calls — HARD),
`R2.CODE-05` (test fixture pattern: local `fixtures_dir`),
`R3.CONTRACT-11` (existing customer tests must not regress).

**Files.**
```
src/haandvaerker/api/customers.py                     (edit — repeat-job)
tests/test_economic_customers.py                      (new — import/list coverage)
tests/test_economic_customers_sync.py                 (edit — expand sync coverage from P2)
tests/test_customers_address_history.py               (new)
tests/test_customers_repeat_job.py                    (new)
tests/fixtures/economic_customers_sample.csv          (read-only — created in P1)
```

These are the ONLY paths the implementer may touch in Phase 3.

**Dependencies.** Phases 1 and 2.

**Acceptance criteria.**

1. `pytest tests/test_economic_customers.py
   tests/test_economic_customers_sync.py
   tests/test_customers_address_history.py
   tests/test_customers_repeat_job.py -x` passes; all four
   test files exist with at least the cases listed below
   (counted via `pytest --collect-only -q`):
   - `test_economic_customers.py`: ≥4 tests (import success,
     import malformed → 422, import duplicate → 409, list by
     company). Note: sync coverage lives in
     `test_economic_customers_sync.py`.
   - `test_economic_customers_sync.py`: ≥5 tests (the Phase 2
     baseline sync-all test PLUS: sync new customer creates,
     sync already-linked returns 200, single-sync of a
     blank-name record returns 422 with the Danish detail
     string, sync-all with a blank-name record reports it in
     `skipped` and includes a `warnings` entry naming the
     `economic_customer_number`).
   - `test_customers_address_history.py`: ≥3 tests
     (case-insensitive substring match across Projects,
     across HistoricalOffers, missing customer → 404).
   - `test_customers_repeat_job.py`: ≥4 tests (success creates
     Project + Quote and returns both, inactive customer →
     422, missing customer → 404, empty title → 422).
2. `grep "repeat-job" src/haandvaerker/api/customers.py`
   returns at least 1 line.
3. `grep "session.flush" src/haandvaerker/api/customers.py`
   shows the flush appears between the Project create and the
   Quote create within the repeat-job handler — verified by
   code reading + a test that intentionally fails Quote
   validation (zero-length title) and asserts no Project row
   exists after the failed transaction.
4. `pytest tests/ -x` passes (no regression in existing test
   files, including the 9 tests in `tests/test_customers.py`
   per R3.CONTRACT-11).
5. `ruff check --select E711,E722,F841,F401,B006,B007,S106,RUF100
   src/haandvaerker/api/customers.py tests/` returns zero
   findings.
6. The repeat-job handler raises `HTTPException(404)` when the
   customer is missing and `HTTPException(422)` when the
   customer is inactive — verified by the two corresponding
   tests in (1).

**Deletions.**

- Any temporary scaffolding comments left in
  `api/economic_customers.py` from Phases 1–2 (e.g. `# TODO:
  add tests in phase 3`). List each removal explicitly in the
  commit message.

**Subtraction check.** Can this phase be achieved purely by
deletion? **No** — the repeat-job endpoint is a new capability.
However, the test-addition portion deliberately *consolidates*
the new endpoints' coverage into three focused files instead
of scattering tests into `test_customers.py` (which would have
grown past 300 lines and become hard to navigate). The
subtraction is in organisational complexity, not LoC.

**Net LoC intent.** ~120 net additions in src (repeat-job
handler ~40, helper extraction if needed ~20) and ~250 net
additions in tests. Tests are not flagged by the minimalism
gate — coverage is the deliverable.

**Rollback.** `git revert` the phase commit; no schema change.
The router's other new endpoints from Phase 2 remain functional.

---

## Cross-cutting concerns

- **D1=B documentation.** Phase 1 adds a comment block in
  `database.py` near `create_db_and_tables()` stating: "D1=B —
  no Alembic; rely on `reset_demo.bat` dropping
  `haandvaerker.db` before any schema-change test cycle.
  `create_all()` is a no-op for new columns on existing tables.
  Pay-down: next schema change touching production-shaped data
  must bootstrap Alembic first." The phase-verifier checks for
  this in Phase 1 acceptance criterion 7.
- **Idempotency.** Sync endpoints are idempotent by D3 (already
  linked → 200 with existing Customer). Import endpoints are
  idempotent by the compound unique index (409 on duplicate
  business key).
- **Audit trail.** Sync responses return `cvr_masked` (R3.RISK-03)
  — the masked value is the audit signal that the correct CVR
  was matched. Raw CVR is never returned, even to confirm a
  sync.
- **CVR multi-match.** Documented inline near every CVR query
  with the comment `# D2: no UNIQUE on cvr_number, first active
  match wins`. Surfaces the trade-off for future readers.
- **Route ordering.** Phase 1 establishes the `economic_customers`
  router with a banner comment citing R3.CONTRACT-10 (fixed
  before parameterised). Phase 2 adds the routes in that order.
  The implementer must register `/sync-all` BEFORE `/{id}/sync`
  in the source file.
- **`models/__init__.py` exports.** Phase 1 adds the three new
  classes to both the import line and `__all__` per R1.CODE-11.
- **Tests.** Phase 3 owns most new test files. Phase 2 has a
  single narrow exception: `tests/test_economic_customers_sync.py`
  is created in Phase 2 with the sync integration test (Phase 2
  AC 8) so the sync-all contract is mechanically verified at the
  phase boundary, not deferred. Phase 3 expands that file with
  additional cases. Phase 1 adds no tests of its own. The repo
  stays working between phases because the existing test suite
  passes (no regressions) and the rest of the new endpoints
  have no dedicated coverage until Phase 3.
- **Sync failure mode for invalid `EconomicCustomer` records**
  (R3.RISK-09). `CustomerBase.name` has `min_length=1`, so a
  stored `EconomicCustomer` with a blank / whitespace-only `name`
  would raise `pydantic.ValidationError` when sync-all attempts
  `CustomerCreate(name='', company_id=...)`. Resolution differs
  by endpoint:
  - **Batch sync (`POST /economic-customers/sync-all`)** uses a
    **per-record skip-with-counter** strategy. If a record fails
    `CustomerCreate` validation (e.g. blank name after `.strip()`),
    increment the `skipped` counter and continue to the next
    record. Do NOT abort the batch. The caller receives the
    final response:
    ```
    {
      "matched": int,
      "created": int,
      "skipped": int,           # includes BOTH no-CVR records AND validation-failed records
      "warnings": list[str]     # one entry per skip-with-reason
    }
    ```
    Each `warnings` entry is a Danish human-readable message
    such as `"Sprang over Kundenummer 42: tomt navn"`. The
    `warnings` key MUST always be present in the response (empty
    list when no skips), so callers can rely on the shape.
  - **Single sync (`POST /economic-customers/{id}/sync`)** with
    a blank-name record fails loud per Iron Law 2:
    `raise HTTPException(422, detail="Kundekort har tomt navn — kan ikke oprette kunde")`.
    A single targeted sync that cannot satisfy its contract
    must surface the error to the caller, not silently skip.
  - This is the canonical asymmetry: batch endpoints
    skip-and-report; single-resource endpoints fail loud. Both
    paths log the offending `economic_customer_number` (WARN
    level for batch; included in the 422 detail for single).
- **No frontend impact.** This repo has no frontend yet (per
  `AGENTS.md`). The frontend-lint gate is N/A.

## Out of scope

- **No Alembic bootstrapping** (D1=B). Deferred until a future
  schema change cannot tolerate a demo reset.
- **No UNIQUE constraint on `Customer.cvr_number`** (D2).
  Deferred to a future Customer-dedup plan.
- **No upsert on EconomicCustomer import.** Duplicates always
  reject with 409, matching the EconomicInvoice contract.
- **No update of existing Customer fields when sync finds a CVR
  match.** Sync is a pure link operation. Field refresh
  (e.g. overwriting `address` from EconomicCustomer.address) is
  out of scope.
- **No fix for `_next_quote_number()` consuming a sequence number
  per empty shell quote** (R3.RISK-05). Accepted for the demo.
- **No EconomicCustomer update / delete endpoint.** Only import,
  list, and the two sync endpoints.
- **No FK from `EconomicInvoice` to `Customer` or
  `EconomicCustomer`.** Out of scope — invoices still reference
  customers by `customer_name` only.
- **No address normalisation** (postal code validation, address
  parsing into street/city). Free-text only, D4 case-insensitive
  substring.
- **No batch endpoint for repeat-job.** Single customer at a
  time.
- **No new frontend / UI.** This repo has no frontend.

## Open questions for the user

None. All decision points (D1–D6) were resolved by the user in
the research brief. The plan is ready for plan-verifier review.

## Review invocation

After Phase 3 verifies PASS, invoke the `review` skill on
`git diff main...HEAD`. The review skill picks its own reviewer
count and concerns; expect at least one reviewer on the schema
+ migration discipline (D1=B follow-through), one on the
endpoint contracts (404/422/409 fidelity), and one on the
masking invariant (cvr_number remains masked end-to-end after
the `CustomerRead` change in Phase 2).
