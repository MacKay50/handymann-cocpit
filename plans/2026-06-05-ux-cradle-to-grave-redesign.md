# Plan: UX/Logik-redesign — Cradle to Grave (8-phase)

**Path:** plans/2026-06-05-ux-cradle-to-grave-redesign.md
**Created:** 2026-06-05
**Research:** research/2026-06-05-ux-cradle-to-grave-redesign/
**Status:** approved

## Research anchors

All artifacts live under
`research/2026-06-05-ux-cradle-to-grave-redesign/` (gitignored —
regenerate via `develop-conductor` if missing):

- `research/2026-06-05-ux-cradle-to-grave-redesign/meta.json` —
  slug, three researchers, status `synthesised`, plan path.
- `research/2026-06-05-ux-cradle-to-grave-redesign/brief.md` —
  synthesised brief the user approved; full decision log
  (DP-1…DP-5), risk highlights, proposed 8-phase structure.
- `research/2026-06-05-ux-cradle-to-grave-redesign/researcher-1-code-contract.json`
  — `CODE-01…12` (auth baseline, model gaps, frontend CID),
  `CONT-01…10` (dependency shape, schema contracts, missing
  endpoints).
- `research/2026-06-05-ux-cradle-to-grave-redesign/researcher-2-impact-risk.json`
  — `IMPACT-01…10` (test blast radius, router inventory,
  `create_all` no-op, nav HTML inventory), `RISK-01…10` (session
  forgeability, body-`company_id` bypass, reminder crash window,
  project false positives, quote type lock-in, inbox
  customer-unknown).
- `research/2026-06-05-ux-cradle-to-grave-redesign/researcher-3-options.json`
  — `OPT-A` (session mechanism), `OPT-B` (scheduler), `OPT-C`
  (e-conomic sync), `OPT-D` (nav). User-resolved to A2 / B2 / C1 /
  D2 plus DP-5 (raw SQL migrations).

Phases below cite specific finding IDs (`CODE-02`, `RISK-02`,
`OPT-A2`) where each decision is anchored.

## Problem

The håndværker system is a greenfield FastAPI + SQLModel + SQLite
app with zero authentication. `company_id` is a forgeable
query-parameter on the list endpoints and a body field on the
create endpoints across 32 router files / 207 endpoints
(`CODE-01`, `CODE-02`, `IMPACT-02`). Thirteen model fields needed
by the new UX are absent across six models (`CODE-03…08`,
`CONT-10`). There is no unified intake path, no qualification
gate, no quote-type enforcement, no task-linked time entries, no
automatic reminder job, no project-close gate, no consistent
navigation, and no Invoice↔EconomicInvoice link. This plan
delivers eight interconnected improvements in eight commit-worthy
phases. The most cross-cutting change — moving `company_id` from
caller-supplied input to a signed-cookie session context — lands
first (Phase 1) so every later phase builds on `CompanyContextDep`
rather than re-introducing the bypass it removes (`RISK-02`).

## Approach

Eight sequential phases, each scoped to a single concern, each
leaving the repo green. The cross-cutting decisions are
**locked** by the user in `brief.md` and must NOT be re-opened:

- **DP-1 / `OPT-A2`** — session context via signed cookie
  (`itsdangerous`). `POST /session/select-company` sets the
  cookie; a shared `get_company_context` dependency validates it
  on every request; `company_id` leaves all query params and all
  Create-schema bodies.
- **DP-2 / `OPT-B2`** — daily reminders via a new
  `POST /jobs/run-reminders` endpoint invoked by OS-cron. Zero new
  Python deps for this phase (the only new dep in the whole plan
  is `itsdangerous`, added in Phase 1).
- **DP-3 / `OPT-C1`** — reuse the existing CSV import +
  `sync-all` infrastructure; no e-conomic REST client.
- **DP-4 / `OPT-D2`** — JS-injected `nav.js` + a
  `/static` mount; zero server-side route changes for nav.
- **DP-5** — schema migrations as numbered raw-SQL scripts in
  `migrations/`; no Alembic (dev environment, no production data).

Phase 1 is the largest and the only high-complexity phase
(`IMPACT-01`: 29 test files + ~30 create schemas + all routers).
Phases 2–8 are smaller, independent, standard-complexity slices
that each consume the Phase-1 context.

## Architectural posture

This plan **redesigns one incumbent pattern** (company-context
sourcing) and **extends several others**.

**Redesign — the company-context pattern.** Today `company_id` is
sourced three ways: optional query filter on lists, required query
param on admin endpoints, and a required body field on creates
(`CODE-02`, `IMPACT-02`, `RISK-02`). This is a `strained` pattern:
every new endpoint must re-decide where `company_id` comes from,
and every create endpoint is a tenant-isolation bypass waiting to
happen. The options-researcher surfaced four mechanisms
(`OPT-A1…A4`); the user selected `OPT-A2` (signed cookie). The new
shape is a single shared `dependencies.py` module exporting
`get_company_context` → `CompanyContextDep`, the *only* sanctioned
source of `company_id`. This is subtraction, not rearrangement:
~30 query-param declarations and ~6 body fields are *removed*; one
canonical source replaces three ad-hoc ones.

**Extend — the "router file per resource" pattern** (`OPT-C1`,
`OPT-D2`, vision §5 "flad struktur"). New routers (`session.py`,
`intake.py`, `jobs.py`) and new endpoints follow the established
shape and register in `main.py`. The e-conomic sync panel reuses
the existing `sync-all` endpoint (`CONT-09`) — no new sync path.

**Extend — `create_all`-only schema management** (DP-5). The
existing `database.py` comment already flags `create_all` as a
no-op for new columns on existing tables. We extend with a
`migrations/` directory of raw SQL, deliberately *not* adopting
Alembic.

**Four-dimension fit:**

- **Separation.** Policy (qualification checklist, completion
  blockers, quote-type rules, reminder thresholds) lives in
  service functions / dedicated modules, not inline in handlers
  (vision §7, AGENTS rule 8). Transport (cookie signing) is
  isolated in `dependencies.py`. The context dependency is the one
  boundary all routers cross for tenancy.
- **Pick-up-ability.** A new engineer learns one rule — "tenancy
  comes from `CompanyContextDep`, never from the request" — and
  every router reads the same. The `migrations/` directory makes
  schema history a flat, ordered, greppable list.
- **Extensibility.** The next related change (real per-user auth,
  `OPT-A3`) becomes a swap of the *inside* of `get_company_context`
  with no router churn — the dependency boundary already exists.
  The unified `/intake` dispatcher is the template for future
  intake types.
- **Security / stability.** The trust boundary *narrows*: a signed
  cookie is tamper-evident where a query param was not (`RISK-01`),
  and stripping `company_id` from create bodies closes the
  cross-tenant write bypass (`RISK-02`). New failure modes
  (missing/invalid cookie) fail loud with 401 (Iron Law 2), never
  a silent default.

**Debt accrued by extension:**

- **No real user identity (`RISK-01`).** The signed cookie binds a
  *company*, not a *user*; any operator on the machine shares the
  context. Acceptable per vision ("Kunder logger ikke ind"). 
  **Pay-down trigger:** the first multi-user / RBAC requirement
  swaps `get_company_context` internals for `OPT-A3` (JWT).
- **Reminder crash window (`RISK-03`).** SMTP-send precedes commit;
  a crash between them can re-send on the next run. Bounded by the
  existing per-level dedup guard. **Pay-down trigger:** a
  two-phase send-state column if duplicate sends are ever
  observed. Documented in code in Phase 6.
- **No Alembic (DP-5).** Numbered raw SQL only. **Pay-down
  trigger:** first schema change touching production-shaped data.
- **SQLite FK enforcement off (`RISK-08`).** New FKs
  (`action_item_id`, `invoice_id`) are not DB-enforced; relies on
  app-level validation + soft-delete. Documented in Phase 2/5.

## Invariants preserved

- **vision §1 / AGENTS rule 1 (kunden er omdrejningspunktet).**
  Every new resource still hangs off `company_id` → project; new
  FKs validate their parent at write time and fail explicit.
- **vision §3 / AGENTS rule 2 / Iron Law 2 (fejl er synlige).**
  No masking fallbacks. Missing session → 401. Validation failure
  → 422 with field/reason. Not-found → 404. No `except Exception`;
  narrow catches only.
- **vision §2 / Iron Law 3 (LLM anbefaler, kode beslutter).** Fee
  amounts, qualification gates, completion blockers, quote-type
  rules, company isolation — all deterministic code.
- **vision §4 / AGENTS rule 3 (revisionsspor).** `Invoice`,
  `Payment`, `InvoiceReminder` stay append-only / soft-delete.
  Reminder auto-job INSERTs new reminder rows; never UPDATEs
  amounts. Project completion sets status but never deletes.
- **vision §6 / AGENTS rule 4 (følsomme felter maskeres).** CVR /
  CPR / bank account stay masked at Read-schema level. No new
  field added by this plan is sensitive; masking discipline
  untouched.
- **AGENTS rule 6 (UUID-idempotens).** New PKs / FKs are string
  UUIDs. Reminder job idempotent via existing `(invoice_id, level)`
  dedup.
- **AGENTS rule 7 (no ORM in responses).** Every new endpoint
  returns a Pydantic Read schema.
- **vision §5 (flad struktur).** New resources = one router file +
  one model edit + `main.py` registration. No dynamic loading.
- **Iron Law 1 (ask on ambiguity).** DP-1…DP-5 resolved by the
  user; no silent choices remain. Open questions (if any) listed
  at the end.

## Phases

### Phase 1: Session context + company middleware  — HIGH COMPLEXITY

**Goal.** Move `company_id` from query/body to a signed-cookie
session context exposed via one shared `CompanyContextDep`, and
update the full test suite so the green bar is preserved.

**Anchors.** `OPT-A2` (signed cookie), `CODE-01` (zero auth
baseline), `CODE-02` (query+body `company_id` everywhere),
`CONT-01` (per-router `SessionDep`, no shared module), `CONT-08`
(`GET /companies/` is the switcher foundation), `IMPACT-01`
(29 query-param test files + conftest override), `IMPACT-02`
(full router inventory of required vs optional `company_id`),
`RISK-01` (cookie tamper-evidence vs forgeable query param),
`RISK-02` (body `company_id` bypass — mechanical strip rule),
`CODE-11`/`CODE-12` (frontend CID + conftest fixture chain).

**Files.**
```
pyproject.toml                                  (edit — add itsdangerous)
src/haandvaerker/config.py                      (edit — add SECRET_KEY)
src/haandvaerker/dependencies.py                (new — get_company_context, CompanyContextDep, CompanyContext, re-export get_session)
src/haandvaerker/api/session.py                 (new — select-company / current / logout)
src/haandvaerker/main.py                        (edit — register session router)
src/haandvaerker/api/*.py                       (edit — ALL 32 routers: swap to CompanyContextDep, drop company_id params)
src/haandvaerker/models/*.py                    (edit — strip company_id from ALL Create schemas that carry it)
tests/conftest.py                               (edit — override get_company_context; drop company_id query/body args)
tests/*.py                                      (edit — all files that pass company_id as query/body)
tests/test_session.py                           (new)
```

These are the ONLY paths the implementer may touch in Phase 1.
The wildcard `api/*.py` and `models/*.py` entries are the
mechanical sweep mandated by `RISK-02`; the implementer touches
only the `company_id`-sourcing lines, not unrelated logic.

**Dependencies.** None.

**Acceptance criteria.**
1. `python -m pytest tests/ -v` passes the full suite (zero
   regressions) after the conftest + test-file sweep.
2. `grep -rn "company_id.*Query\|company_id.*Body" src/haandvaerker/api/ | grep -v "session.py"`
   returns zero matches (no stray `company_id` query/body input params
   outside the session router — path params and Read-schema fields are
   intentionally excluded from this check).
3. `POST /session/select-company` with a valid `company_id` sets a
   signed cookie and returns 200; `GET /session/current` returns
   the active company.
4. Any endpoint called without a valid session cookie returns 401
   with a clear `detail` message (verified by a `test_session.py`
   case).
5. `grep -n "itsdangerous" pyproject.toml` returns exactly one
   match — the ONLY new dependency added by the whole plan.
6. `python -c "from haandvaerker.dependencies import get_company_context, CompanyContextDep; print('ok')"`
   prints `ok` (shared module importable per `CONT-01`).
7. `ruff check --select E711,E722,F841,F401,B006,B007,S106,RUF100 src/haandvaerker/dependencies.py src/haandvaerker/api/session.py`
   returns zero findings.

**Deletions.**
- ~30 `company_id` query-parameter declarations across the router
  files (`IMPACT-02` inventory) — replaced by `CompanyContextDep`.
- `company_id` body field from every Create schema that carries it
  (`CustomerCreate`, `InboxMessageCreate`, `ActionItemCreate`,
  `EnquiryCreate`, `QuotePreparationCreate`, and any peer found in
  the sweep) per `RISK-02`.
- Per-router local `SessionDep = Annotated[...]` aliases that are
  now superseded by the shared import are consolidated to the
  shared `dependencies.py` (remove the duplicate definitions, keep
  one import). The implementer lists each removed alias in the
  commit message.

**Subtraction check.** Can this phase be achieved purely by
deletion? **No** — `itsdangerous` signing and the
`get_company_context` dependency are genuinely new mechanism. But
the *net* shape is subtractive: three ad-hoc tenancy sources
collapse to one, and ~36 caller-supplied `company_id` declarations
are removed (deletions above). No parallel implementation is
introduced — every router imports the single shared dependency.

**Net LoC intent.** Mixed. `dependencies.py` ~60, `session.py`
~50, `config.py` ~3, `main.py` ~3 (additions). Router + model
sweep is net-*negative* per file (removing params). Test sweep is
mechanical churn (changing call sites, not adding tests) plus
`test_session.py` ~60. Flagged as the largest phase by file count;
the minimalism gate should read the per-file router/model diffs as
net-negative.

**Rollback.** `git revert` the phase commit. No schema migration
(cookie is stateless, no session table). The `SECRET_KEY` config
addition is inert if unused. Frontend CID continues to function
only after Phase 8 wires the cookie flow; until then the test
suite (cookie via conftest override) is the contract.

---

### Phase 2: Model field additions + migration SQL  — STANDARD

**Goal.** Add 9 nullable/defaulted fields across six models and
write the raw-SQL migration; no endpoint logic changes.

**Anchors.** `CODE-03`/`CONT-04` (TimeEntry `action_item_id`),
`CODE-04`/`CONT-05` (InvoiceReminder `triggered_by`),
`CODE-05`/`CONT-06` (Project `close_reason`, `close_override`),
`CODE-06`/`CONT-07` (Quote `quote_type`),
`CODE-08`/`CONT-03` (Enquiry `address`, `work_type`, `timeframe`),
`CONT-10`/`IMPACT-09` (EconomicInvoice `invoice_id`),
`IMPACT-03/04/06/09` (`create_all` no-op → migration needed;
nullable defaults → no test breakage), `RISK-08` (SQLite FK
enforcement off — document inline). The `create_all` no-op
findings (`IMPACT-03`, `IMPACT-04`) directly motivate the
raw-SQL migration approach (user decision DP-5 in `brief.md`).

**Files.**
```
src/haandvaerker/models/time_entry.py           (edit — action_item_id FK + Read)
src/haandvaerker/models/invoice_reminder.py      (edit — triggered_by + Read)
src/haandvaerker/models/project.py               (edit — close_reason, close_override + Read)
src/haandvaerker/models/quote.py                 (edit — quote_type default 'line' on table + Read; NOT QuoteCreate yet)
src/haandvaerker/models/enquiry.py               (edit — address, work_type, timeframe + Read)
src/haandvaerker/models/economic_invoice.py      (edit — invoice_id FK + Read)
migrations/001_ux_redesign_fields.sql            (new — 8 ALTER TABLE ADD COLUMN)
tests/test_model_fields.py                       (new — assert each field present + defaulted)
```

These are the ONLY paths the implementer may touch in Phase 2.

**Dependencies.** Phase 1 (in-memory test DB uses `create_all`;
new fields appear automatically — `IMPACT-04`).

**Acceptance criteria.**
1. `python -m pytest tests/ -v` passes (all new fields
   nullable/defaulted → no existing test breaks per
   `IMPACT-03/04/06/09`).
2. `migrations/001_ux_redesign_fields.sql` contains exactly 8
   `ALTER TABLE ... ADD COLUMN` statements — verified by
   `grep -c "ADD COLUMN" migrations/001_ux_redesign_fields.sql`
   returning 8.
3. `python -m pytest tests/test_model_fields.py -v` passes,
   asserting each of the 13 new fields appears on its Read schema
   with the documented default (`triggered_by='manual'`,
   `quote_type='line'`, `close_override=False`, others
   nullable/`None`).
4. `ruff check --select E711,E722,F841,F401,B006,B007,S106,RUF100 src/haandvaerker/models/`
   returns zero findings on touched files.

**Deletions.** None. Pure additive schema slice — there is no
prior version of these fields to remove (`CODE-03…08`, `CONT-10`).
The implementer surfaces and removes any incidental dead
TODO/stub uncovered while editing the models, listing each in the
commit message.

**Subtraction check.** Can this phase be achieved purely by
deletion? **No** — the fields do not exist anywhere (research
confirms). Mitigation against additive sprawl: each field is a
single column with a default, added to the table + Read schema
only; no new service modules, no parallel schemas. The 8 columns
are consolidated into ONE migration file, not eight.

**Net LoC intent.** ~50 across six model files + ~10 SQL + ~40
test. Under the soft-flag threshold per file.

**Phase 8 reminder (DAT-01).** `_to_read` in
`api/economic_invoices.py` constructs `EconomicInvoiceRead`
explicitly and must add `invoice_id=obj.invoice_id` in Phase 8
so the stored link is visible through GET responses.

**Rollback.** `git revert` the phase commit. For local DBs that
already ran `001_ux_redesign_fields.sql`: drop and recreate via
the demo reset (DP-5 contract — documented in the migration file
header). `create_all` is a no-op for the reverted columns, so no
stale-column error on next boot.

---

### Phase 3: Unified Inbox + Guided Qualification  — STANDARD

**Goal.** One `POST /intake` dispatcher for new tasks; a
qualification checklist gating enquiry conversion.

**Anchors.** `CONT-02` (three separate create flows to
consolidate), `RISK-10` (InboxMessage has no customer FK —
customer-unknown must be graceful), `CONT-03` (no
qualification-status endpoint; `qualify` is a blind transition),
`CODE-08` (enquiry fields — `address`/`work_type` now present from
Phase 2), `CODE-07` (ActionItem create contract).

**Files.**
```
src/haandvaerker/api/intake.py                   (new — POST /intake discriminated union)
src/haandvaerker/main.py                         (edit — register intake router)
src/haandvaerker/api/enquiries.py                (edit — GET /{id}/qualification-status; gate on POST /{id}/convert)
src/haandvaerker/services/enquiry_qualification.py (new — checklist policy function)
tests/test_intake.py                             (new)
tests/test_enquiry_qualification.py              (new)
```

These are the ONLY paths the implementer may touch in Phase 3.

**Dependencies.** Phase 1 (session context for `company_id`),
Phase 2 (`Enquiry.address`, `Enquiry.work_type`).

**Acceptance criteria.**
1. `POST /intake` with `type='message'` creates an `InboxMessage`
   and returns 201 with `{"type": "message", "id": "..."}`;
   `type='project_task'` creates an `ActionItem` with `project_id`;
   `type='internal_task'` creates an `ActionItem` without
   `project_id`. `company_id` is taken from the session for all
   three, never from the body (`RISK-02`).
2. `POST /enquiries/{id}/convert` returns 422 (with the missing
   checklist items in `detail`) when qualification is not ready,
   and 200 when ready.
3. `GET /enquiries/{id}/qualification-status` returns
   `{ready: bool, checklist: [...], missing_fields: [...]}`. The 5
   gates are: `contact_name` non-null; (`contact_email` OR
   `contact_phone`) non-null; `notes` non-null; `address` non-null;
   `work_type` non-null — all 5 required for `ready: true`.
4. `python -m pytest tests/test_intake.py tests/test_enquiry_qualification.py -v`
   passes.
5. The checklist logic lives in
   `services/enquiry_qualification.py` (policy separated from
   transport per vision §7) — verified by
   `grep -n "def " src/haandvaerker/services/enquiry_qualification.py`
   showing the gate function, and the convert handler importing it.

**Deletions.** None required by the new capability. If the
existing `POST /{id}/qualify` blind transition becomes redundant
with the new gated `convert`, the implementer either keeps it
(distinct status step) or removes it — decision surfaced to the
user, not made silently (Iron Law 1). Default: keep `qualify` as
the status transition, add the gate only to `convert`.

**Subtraction check.** Can this phase be achieved purely by
deletion? **No** — the dispatcher and the gate are new behaviour.
Mitigation: `/intake` *routes to existing* create handlers rather
than duplicating their logic (`CONT-02`); the checklist is one
shared policy function reused by both the status endpoint and the
convert gate — no parallel checks.

**Net LoC intent.** ~70 (intake router ~40, qualification service
~25, enquiry edits ~20) + ~80 test. Within threshold.

**Rollback.** `git revert` the phase commit; no schema change
(fields landed in Phase 2). The `convert` gate reverts to its
prior ungated behaviour.

---

### Phase 4: Quote type enforcement  — STANDARD

**Goal.** Require explicit `quote_type` at creation and prevent
cross-type pollution on update.

**Anchors.** `CODE-06`/`CONT-07` (no type discriminator; lines and
rooms coexist; totals computed only from lines), `RISK-09` (PATCH
can mix types — enforce on create AND update), `IMPACT-06`
(existing quotes default to 'line' safely).

**Files.**
```
src/haandvaerker/models/quote.py                 (edit — quote_type required on QuoteCreate, optional on QuoteUpdate)
src/haandvaerker/api/quotes.py                    (edit — enforce type rules at create + update; route totals)
tests/test_quotes.py                              (edit — add quote_type cases)
```

These are the ONLY paths the implementer may touch in Phase 4.

**Dependencies.** Phase 1 (session), Phase 2 (`Quote.quote_type`
column + Read schema already present).

**Acceptance criteria.**
1. `POST /quotes/` with `quote_type='line'` and a non-empty
   `rooms` list returns 422; with `quote_type='area'` and a
   non-empty `lines` list returns 422.
2. Area-quote totals are computed from room m² × `price_per_m2`;
   if `price_per_m2` is absent on any room in an area-type quote,
   the endpoint returns 422 — never a silent zero (vision §3,
   Iron Law 2). Line-quote totals unchanged.
3. Existing quote tests pass (existing quotes had lines and now
   default to `quote_type='line'` — `IMPACT-06`).
4. `PATCH /quotes/{id}` that changes `quote_type` validates that
   existing lines/rooms are compatible or clears the incompatible
   collection, returning 422 if it cannot reconcile (`RISK-09`).
5. `python -m pytest tests/test_quotes.py -v` passes.

**Deletions.** The unconditional both-collections build in the
`POST /quotes/` handler (`quotes.py` lines ~141-160) is *replaced*
by type-gated branches — the old unconditional path is removed,
not left beside the new one. Listed in the commit message.

**Subtraction check.** Can this phase be achieved purely by
deletion? **No** — type enforcement is new validation. But it
removes a latent-bug path (mixed-type quote with `subtotal=0`,
`CODE-06`); net effect is a *narrower* set of reachable states.

**Net LoC intent.** ~40 src + ~40 test. Within threshold.

**Rollback.** `git revert` the phase commit; no schema change.
Quotes created during the phase keep their `quote_type` value
(harmless under the reverted ungated handler).

---

### Phase 5: TimeEntry task linking  — STANDARD

**Goal.** Optional `action_item_id` on time entries with
same-project validation; a project time-summary grouped by task.

**Anchors.** `CODE-03`/`CONT-04` (`action_item_id` FK, now present
from Phase 2), `IMPACT-04` (18 existing tests pass with nullable
field), `RISK-08` (ActionItem soft-delete; FK not DB-enforced —
validate in app), brief §"Time registration with task linking"
("Generelt" fallback label).

**Files.**
```
src/haandvaerker/api/time_entries.py             (edit — accept/validate action_item_id on create + update)
src/haandvaerker/api/projects.py                 (edit — GET /projects/{id}/time-summary)
tests/test_time_entries.py                        (edit — action_item_id cases)
tests/test_project_time_summary.py                (new)
```

These are the ONLY paths the implementer may touch in Phase 5.

**Dependencies.** Phase 1 (session), Phase 2
(`TimeEntry.action_item_id` column).

**Acceptance criteria.**
1. `POST /time-entries/` with a valid `action_item_id` whose
   ActionItem is in the same project succeeds.
2. `POST /time-entries/` with an `action_item_id` from a different
   project returns 422 (validate `ActionItem.project_id ==
   TimeEntry.project_id`, `RISK-08`).
3. `GET /projects/{id}/time-summary` returns entries grouped:
   `[{action_item_id, label, total_hours, entries: [...]}]`.
4. Null-`action_item_id` entries appear under `{label: "Generelt"}`.
5. Linking a new entry to a soft-deleted (`active=False`)
   ActionItem succeeds but is flagged (warning in the response or
   log) rather than rejected, since existing entries stay valid
   (`RISK-08`).
6. `python -m pytest tests/test_time_entries.py tests/test_project_time_summary.py -v`
   passes.

**Deletions.** None expected — additive linking on an existing
resource. Implementer removes any incidental dead code surfaced.

**Subtraction check.** Can this phase be achieved purely by
deletion? **No** — the link + grouping are new behaviour. The
grouping endpoint reuses existing time-entry queries; no new
service module is introduced for it.

**Net LoC intent.** ~50 src + ~60 test. Within threshold.

**Rollback.** `git revert` the phase commit; no schema change
(column landed Phase 2). Entries created with `action_item_id` are
harmless once the validation is reverted.

---

### Phase 6: Automatic reminder job  — STANDARD

**Goal.** A daily endpoint that finds overdue invoices and creates
/ sends reminders automatically at +7 / +14 / +21 days.

**Anchors.** `OPT-B2` (endpoint-triggered cron), `CODE-04`
(`triggered_by` now present from Phase 2; existing
`send_or_generate_reminder` + per-level dedup),
`CONT-05` (`sent_by='scheduler'` convention),
`CODE-09` (no scheduler exists — endpoint only), `CODE-10`
(SMTP path reusable verbatim), `RISK-03` (crash window —
document), `RISK-04` (fee constants already correct in config),
`RISK-06` (multi-worker safe — one HTTP request from cron).

**Files.**
```
src/haandvaerker/api/jobs.py                      (new — POST /jobs/run-reminders)
src/haandvaerker/services/invoice_reminder_service.py (edit — run_automatic_reminders(session, company_id))
src/haandvaerker/main.py                          (edit — register jobs router)
tests/test_jobs.py                                (new)
```

These are the ONLY paths the implementer may touch in Phase 6.

**Dependencies.** Phase 1 (session), Phase 2
(`InvoiceReminder.triggered_by`).

**Acceptance criteria.**
1. `POST /jobs/run-reminders` (company_id from session) triggers
   the reminder logic and returns
   `{processed: int, sent: int, queued_for_review: int, errors: list[str]}`.
2. An invoice 8 days overdue with no reminder gets a level-1
   `InvoiceReminder` created (`fee=0`, `triggered_by='auto'`,
   `sent_by='scheduler'`); calling the endpoint again creates no
   duplicate (existing `(invoice_id, level)` dedup, `RISK-03`).
3. A level-3 reminder is created with `triggered_by='auto'` but
   `method='manual'` (NOT auto-sent — marked for manual review).
4. Level-2 uses `REMINDER_FEE_ORE_2`; thresholds are +7/+14/+21
   days on `due_date` for `status='sent'` invoices (`RISK-04`).
5. `python -m pytest tests/test_jobs.py -v` passes.
6. The crash-window limitation (`RISK-03`) is documented in a
   comment in `run_automatic_reminders` — verified by
   `grep -n "RISK-03\|crash window\|krasvindue" src/haandvaerker/services/invoice_reminder_service.py`.

**Deletions.** None. The job *reuses* `send_or_generate_reminder`
rather than reimplementing send logic (`CODE-10`); only a new
batch-orchestration function and a thin endpoint are added.

**Subtraction check.** Can this phase be achieved purely by
deletion? **No** — automatic invocation does not exist
(`CODE-09`). Mitigation: zero new dependencies (`OPT-B2`); the
batch function delegates each send to the existing single-send
service; idempotency reuses the existing guard.

**Net LoC intent.** ~40 (jobs router ~20, service function ~50)
src + ~60 test. Service function may approach the soft-flag
threshold; justified — it owns the three-threshold batch logic in
one place.

**Rollback.** `git revert` the phase commit; no schema change.
Reminders already created stay (append-only, vision §4); OS-cron
entry is operator-managed and documented in cross-cutting.

---

### Phase 7: Project close checklist  — STANDARD

**Goal.** Server-side completion validation with an override path
that records a reason — without touching `PATCH /projects/{id}`.

**Anchors.** `CODE-05`/`CONT-06` (`close_reason`/`close_override`
now present; no completion gate today; PATCH sets status
unconditionally), `IMPACT-05` (`economic_invoices.py:282` sets
`status=completed` via ORM — gate must be a *separate* endpoint,
NOT on PATCH), `RISK-05` (internal projects with only non-billable
entries pass vacuously).

**Files.**
```
src/haandvaerker/services/project_service.py      (new — check_completion_status(session, project_id))
src/haandvaerker/api/projects.py                  (edit — GET /completion-status, POST /complete)
tests/test_project_completion.py                  (new)
```

These are the ONLY paths the implementer may touch in Phase 7.

**Dependencies.** Phase 1 (session), Phase 2
(`Project.close_reason`, `Project.close_override`).

**Acceptance criteria.**
1. `GET /projects/{id}/completion-status` returns
   `{ready: bool, blockers: [...], warnings: [...]}`. Blockers (1)
   unbilled billable TimeEntries, (2) unbilled billable Expenses,
   (3) no paid Invoice when invoices exist; warning (4) open /
   in_progress active ActionItems (soft, non-blocking).
2. `POST /projects/{id}/complete` without `close_reason` on a
   blocked project returns 422 with the checklist.
3. `POST /projects/{id}/complete` with `close_reason` on a blocked
   project returns 200, sets `status='completed'`,
   `close_override=True`, and stores the reason.
4. A project with only non-billable (`billable=False`) entries
   returns `ready=true` (vacuous pass, `RISK-05`).
5. `PATCH /projects/{id}` is NOT modified — verified by
   `git diff` showing no change to the `update_project` handler;
   the `economic_invoices.py:282` ORM path stays open
   (`IMPACT-05`).
6. `python -m pytest tests/test_project_completion.py -v` passes.

**Deletions.** None. The new gate is added as a dedicated endpoint
beside the untouched PATCH, deliberately (per `IMPACT-05`, the ORM
completion path must remain). No prior gate exists to remove.

**Subtraction check.** Can this phase be achieved purely by
deletion? **No** — the gate is new policy. Mitigation: the blocker
logic lives in one `project_service.check_completion_status`
function reused by both `completion-status` (read) and `complete`
(write); no duplicated checks.

**Net LoC intent.** ~60 (service ~40, endpoints ~30) src + ~70
test. Service near threshold; justified — single policy home.

**Rollback.** `git revert` the phase commit; no schema change.
Projects completed via the new endpoint keep `close_override` /
`close_reason` (harmless columns).

---

### Phase 8: Navigation + e-conomic sync panel + EconomicInvoice link  — STANDARD

**Goal.** Consistent JS-injected nav across all pages, a sync
panel reusing the existing endpoint, and a manual
Invoice↔EconomicInvoice link.

**Anchors.** `OPT-D2` (JS-injected `nav.js` + `/static` mount),
`IMPACT-10` (8 static HTML files; tab bar in `ui.html`),
`CONT-09`/`IMPACT-08` (existing `sync-all` reused — no new sync
endpoint), `CONT-10`/`IMPACT-09` (EconomicInvoice `invoice_id` now
present from Phase 2; new PATCH link endpoint; no auto-link),
`CODE-11` (frontend CID — nav.js carries the company switcher that
now drives the Phase-1 session cookie).

**Files.**
```
src/haandvaerker/static/nav.js                    (new — nav HTML + company switcher + [+ Ny] button)
src/haandvaerker/main.py                          (edit — app.mount /static StaticFiles)
src/haandvaerker/static/*.html                    (edit — add <script src="/static/nav.js"> before </body> on all 8 pages)
src/haandvaerker/api/economic_invoices.py         (edit — PATCH /{id}/link-invoice)
src/haandvaerker/models/economic_invoice.py       (edit — invoice_id on EconomicInvoiceUpdate if not already exposed)
tests/test_economic_invoice_link.py               (new)
```

These are the ONLY paths the implementer may touch in Phase 8.

**Dependencies.** Phase 1 (session — switcher POSTs to
`/session/select-company`), Phase 2 (`EconomicInvoice.invoice_id`
column + Read schema).

**Acceptance criteria.**
1. `GET /static/nav.js` returns 200 with JavaScript content (the
   `/static` mount exists per `OPT-D2`).
2. `grep -l "nav.js" src/haandvaerker/static/*.html | wc -l`
   equals 8 (all pages include the script tag, `IMPACT-10`).
3. `PATCH /economic-invoices/{id}/link-invoice` with a valid
   `invoice_id` returns 200 with `invoice_id` set; with
   `invoice_id: null` clears the link (`CONT-10`).
4. `PATCH /economic-invoices/{id}/link-invoice` with an
   `invoice_id` from a different company returns 422 (company
   isolation from session, `RISK-02`).
5. `python -m pytest tests/test_economic_invoice_link.py -v`
   passes.

**Deletions.** **Plan correction (Phase 8 implementation):** The
`ui.html:371-382` `.tabs` div was retained — it drives intra-page
section switching via `data-tab`/`showTab()` and is NOT replaced
by `nav.js` (which provides cross-page navigation). Removing it
would break the dashboard. `nav.js` and the inline tabs are
complementary, not duplicates. Any other duplicated topbar-link
markup superseded by `nav.js` is removed from edited HTML pages.

**Subtraction check.** Can this phase be achieved purely by
deletion? **No** — `nav.js`, the `/static` mount, and the link
endpoint are new. But `OPT-D2` is the *minimum-touch* option (zero
server route changes for nav), the sync panel adds NO new endpoint
(reuses `sync-all`, `CONT-09`), and the inline tab-bar deletion
removes duplicated nav markup.

**Net LoC intent.** `nav.js` ~120 (single source for all-page nav
— justified vs the `OPT-D4` per-page duplication it replaces),
link endpoint ~30 src + ~40 test, HTML edits small. `nav.js` is
flagged above 100 lines; justified as the single nav source of
truth (`OPT-D2` consistency rationale).

**Rollback.** `git revert` the phase commit; no schema change
(column landed Phase 2). Removing the `/static` mount and the
script tags restores the prior inline nav (also reverted in the
same commit).

---

## Cross-cutting concerns

- **company_id isolation (`RISK-02`).** From Phase 1 onward, every
  endpoint derives `company_id` exclusively from
  `CompanyContextDep`; every query filters by it; cross-company
  access returns 422/404. Phases 3–8 each re-assert this in an
  acceptance criterion. The Phase-1 grep gate (AC 2) is the
  mechanical guard against regressions.
- **Migrations (DP-5).** Phase 2 owns `001_ux_redesign_fields.sql`.
  Any later phase needing a new column adds a new numbered file
  (none currently planned — all 13 fields land in Phase 2). The
  migration file header documents the demo-reset rollback
  contract and the `create_all`-no-op limitation.
- **OS-cron setup (Phase 6, `OPT-B2`).** The
  `POST /jobs/run-reminders` endpoint is invoked by an
  operator-configured Windows Task Scheduler / cron entry. This is
  infrastructure outside the codebase; documented in the Phase-6
  commit message and a one-line note in the jobs router docstring.
- **Append-only audit (vision §4).** The reminder job (Phase 6)
  and project completion (Phase 7) INSERT / set-status only; never
  UPDATE amounts, never physical-delete.
- **Policy vs transport (vision §7).** Phase 3 qualification, Phase
  6 reminder thresholds, Phase 7 completion blockers each live in a
  dedicated service module / function, not inline in handlers.
- **Frontend (DP-4).** Phase 8 is the only phase touching static
  HTML / JS. Phases 1–7 keep the test suite (cookie via conftest
  override) as the contract; the browser cookie flow is wired in
  Phase 8 via the `nav.js` company switcher.
- **SQLite FK enforcement off (`RISK-08`).** New FKs
  (`action_item_id`, `invoice_id`) are validated in application
  code (Phases 5, 8), not by the DB. Documented inline at the
  validation sites.
- **Tests.** Each phase adds/updates its own tests and must leave
  `python -m pytest tests/ -v` green. Phase 1 carries the largest
  test churn (the 29-file query-param sweep + `test_session.py`).

## Out of scope

- Full per-user authentication (login, RBAC, password management) —
  the cookie binds a company, not a user (`RISK-01`).
- e-conomic REST API direct integration — CSV-first per `OPT-C1`.
- Auto-linking EconomicInvoice ↔ Invoice — manual link only
  (Phase 8, `CONT-10`).
- Alembic migration framework — raw SQL scripts only (DP-5).
- PWA / offline shell (vision §8 future item).
- Splitting a payment in the reconciliation matcher.
- Betalingsradar UI changes — existing `reconciliation.html` kept
  as-is; `nav.js` only links it under Fakturering.
- Two-phase reminder send (the `RISK-03` crash window is documented
  and accepted, not fixed).
- An "exempt from invoicing" project flag (`RISK-05`) — vacuous
  pass on non-billable entries is the agreed mitigation.
- Multi-worker job locking (`RISK-06`) — `OPT-B2` is multi-worker
  safe by construction (one HTTP request from cron).

## Open questions for the user

None. All five design decisions (DP-1…DP-5) and the 8-phase order
were resolved by the user in `brief.md`. The one in-phase
judgement call (keep vs remove the legacy `POST /{id}/qualify`
blind transition, Phase 3 Deletions) defaults to *keep* and is
surfaced to the user at implementation time per Iron Law 1 rather
than blocking plan approval.

## Review invocation

After Phase 8 verifies PASS, invoke the `review` skill on
`git diff main...HEAD`. The review skill picks its own reviewer
count and concerns; expect at least one reviewer on the
session/tenant-isolation discipline (Phase 1 `company_id` sweep,
`RISK-02`), one on the append-only / fail-loud invariants (Phases
6–7), and one on the migration + schema discipline (Phase 2,
DP-5).
