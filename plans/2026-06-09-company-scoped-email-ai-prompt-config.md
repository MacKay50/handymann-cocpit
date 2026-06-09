# Plan: Company-scoped email / AI / prompt config + settings module

**Path:** plans/2026-06-09-company-scoped-email-ai-prompt-config.md
**Created:** 2026-06-09
**Research:** research/2026-06-09-company-scoped-email-ai-prompt-config/
**Status:** revised (addresses plan-verifier NEEDS REVISION rev 1–4)

## Research anchors

- `research/2026-06-09-company-scoped-email-ai-prompt-config/researcher-1-code+contract.json`
  — call sites for email/SMTP/AI/prompt config, `CompanyContextDep` shape,
  ownership-guard pattern, `create_all()` table-creation semantics, static
  serving layout, masking precedent (`from_orm_masked`), and the wizard
  prompt binding point.
- `research/2026-06-09-company-scoped-email-ai-prompt-config/researcher-2-impact+risk+options.json`
  — import-time-binding impact in `email_poller.py` / `smtp_sender.py`,
  call-time-safe `local_ai.py`, SSRF / plaintext-password / event-loop /
  partial-migration / path-traversal / missing-dir risks, and the five
  table-strategy options (OPT-A..OPT-E).

Phases below cite specific finding IDs (`CODE-05`, `RISK-04`, `OPT-A`, …)
where a decision is anchored in research evidence.

## Problem

The system today reads email (IMAP), outbound mail (SMTP), local-AI
endpoint/model, and the wizard's draft prompts from global `.env`
constants — single-tenant config baked in at module-import time. A
håndværker company has no self-service way to edit its own company master
data, upload a logo, configure its mailbox, point AI at its own endpoint,
or tune the draft prompt. We are building a company-settings module that
moves email / AI / prompt config into per-company DB tables (with the
`.env` values demoted to a logged boot-time fallback), adds a logo-upload
endpoint, exposes a real IMAP/SMTP connection test, and ships a `/settings`
page with a nav entry. This unblocks multi-tenant use and gives the owner
a single screen to configure the integrations that are currently invisible.

## Approach

We take **OPT-A** (three separate DB tables: `CompanyEmailConfig`,
`CompanyAiConfig`, `CompanyPromptConfig`), as locked in the design
decisions and justified in research as the best fit for vision §5 (flat
structure, one resource registered in one place) and §7 (policy separated
from transport). Each table has `company_id` as primary key (one row per
company). New tables are auto-created by the existing `create_all()` on
startup (`CODE-05`) — **no migration file is needed for the three new
tables**, only that their model modules are imported before lifespan
fires. Cross-cutting decisions baked in: (1) passwords never leave the API
— GET returns `password_set: bool` only, matching the `from_orm_masked`
precedent (`CONT-01`); (2) the email/SMTP services are refactored to
**accept credentials as parameters** so the caller resolves per-company
config at call time, killing the import-time binding (`CODE-07`,
`CODE-08`); (3) the connection-test endpoint runs the blocking socket work
in a threadpool via `run_in_executor` with a hard timeout (`RISK-03`,
`IMP-06`); (4) `local_ai` gains optional `endpoint`/`model` parameters
(call-time-safe already, `CODE-09`); (5) DB-first with `.env` fallback is
a **legitimate boot/operator fallback logged once at INFO**, not runtime
masking — but a *partial* migration that silently routes one company's
mail through another's `.env` credentials is the forbidden case
(`RISK-04`), so the email/SMTP cutover lands atomically in one phase;
(6) logo files are named solely from `company_id` + a whitelisted
extension, size-capped at 2 MB, written under a directory created at
startup (`RISK-05`, `RISK-06`).

## Architectural posture

**Incumbent pattern touched: global module-level config constants consumed
at import time by `email_poller.py` and `smtp_sender.py`.** Research grades
this pattern as strained for the multi-tenant goal — `is_configured()` /
`is_smtp_configured()` read frozen globals (`IMP-02`, `IMP-03`), and
`local_ai.py` is the only one of the three already call-time-safe
(`IMP-04`, `CODE-09`). For these two services we are **redesigning**, not
extending: credentials become explicit function parameters
(`send_email(..., cfg)`, `poll_inbox(company_id, session, cfg)`), and the
caller owns config resolution. The options-researcher's redesign
alternative is captured as the parameter-injection direction inside OPT-A's
blast radius; the rejected "keep reading globals" path is OPT-D (do
nothing), which does not answer the problem.

For the three config tables themselves this is a **greenfield addition** —
a new `models/company_config.py` + `api/company_config.py` pair registered
in `main.py` exactly per the "Adding a new resource" workflow (`CONT-04`,
`CONT-05`).

Four-dimension fit:

- **Separation of concerns.** Infrastructure config (mailbox, AI endpoint,
  prompts) lives in dedicated tables and a dedicated router, keeping the
  `Company` master-data table clean (OPT-A beats OPT-C which would pollute
  it). Service modules stop owning policy (where credentials come from);
  they become pure mechanism (given credentials, connect/send).
- **Pick-up-ability.** A new engineer finds all config in one model file,
  one API file, and one settings page. The `password_set` masking mirrors
  the existing `from_orm_masked` convention so the security shape is
  familiar. Resolution helpers (`resolve_email_config(session, company_id)`)
  centralise the DB-first/.env-fallback decision in one named place.
- **Extensibility.** The next related change — per-company AI API keys,
  or a second mailbox — is an added column / added table, not a rewrite,
  because credentials already flow as parameters.
- **Security / stability posture.** This plan widens the trust boundary by
  accepting user-supplied IMAP/SMTP host/port (SSRF surface, `RISK-01`) and
  storing a mail password in SQLite (`RISK-02`). Mitigations: host
  validation rejecting loopback/RFC1918/link-local before any connect
  attempt; password write-only via API and never returned; threadpool +
  hard timeout so a slow server cannot stall the event loop. Plaintext
  password storage is an **accepted known limitation** (out of scope:
  encryption) and is called out for the user.

**Debt accrued by the redesign:** `inbox.py:email_config_status` and the
`smtp_configured` flags in `invoice_reminders.py` currently reflect `.env`
state; after cutover they must reflect DB state. Phase 2 updates them so
the system is not left in a half-migrated state (`CONT-08`, `IMP-02`). No
new debt is deferred beyond the explicitly out-of-scope items.

## Invariants preserved

- **vision §6 / AGENTS rule 4 (sensitive data masked).** Email/SMTP
  password never appears in any GET response — only `password_set: bool`
  (`CONT-01`).
- **vision §3 / AGENTS rule 2 (errors visible, no silent defaults).** The
  connection-test endpoint fails loud with the real error class; missing
  required config fields → 422 with field name; a company with no AI row
  reports AI disabled rather than silently using global `.env` (`RISK-07`,
  `CONT-02`).
- **vision §2 (LLM recommends, code decides).** The wizard prompt fallback
  is a deterministic `if row: use row else: use prompts.py` in Python, never
  delegated to the model (`CONT-03`).
- **vision §5 (flat structure, registered in one place).** Three tables in
  one model file, one router, named imports in `main.py` — no dynamic
  loading (`CONT-05`).
- **vision §7 (config separated from code; policy from transport).** Config
  lives in DB rows; services become credential-agnostic mechanism.
- **`CompanyContextDep` is the only source of `company_id`** — no config
  endpoint accepts `company_id` from path/body; it comes from the session
  cookie (`dependencies.py` contract, `CODE-03`).

## Phases

### Phase 1: Config models + company master-data + logo upload

**Goal.** Land the three config DB tables (models + Read/Update schemas,
auto-created via `create_all()`), confirm/round out `GET`/`PATCH`
`/companies/{id}`, and add a validated logo upload/delete endpoint served
statically.

**Anchors.** `CODE-01` (Company already has logo_ref/phone/email),
`CODE-05` (create_all auto-creates new tables), `CODE-11`/`CODE-12`
(no uploads dir, StaticFiles needs it to exist), `CONT-01` (masking
precedent), `CONT-04`/`CONT-05` (new-resource workflow, flat registration),
`RISK-05` (path traversal), `RISK-06` (missing dir), `OPT-A` (three tables).

**Files.**
```
src/haandvaerker/models/company_config.py        (new)
src/haandvaerker/api/company_logo.py             (new)
src/haandvaerker/main.py                          (register router, mkdir in lifespan, /settings route deferred to Phase 4)
src/haandvaerker/models/company.py                (add logo_url to CompanyRead if absent)
tests/test_company_config_models.py              (new)
tests/test_company_logo.py                        (new)
```
These are the ONLY paths the implementer may touch in this phase. The three
config tables are *defined* here so `create_all()` picks them up, but their
endpoints land in Phases 2–3. Defining a table without its endpoint leaves
the repo working (the table is simply unused until later phases).

**Dependencies.** None.

**Acceptance criteria.**
1. `pytest tests/test_company_config_models.py` passes: instantiating
   `CompanyEmailConfig`, `CompanyAiConfig`, `CompanyPromptConfig` and
   committing to the in-memory DB round-trips; `create_db_and_tables()`
   creates all three tables (assert via `inspect(engine).get_table_names()`).
2. `pytest tests/test_company_logo.py` passes, including: a PNG upload under
   2 MB → 201 and a file at `static/uploads/logos/{company_id}.png`; a
   `.txt` (non-image) → 422; a 3 MB image → 422; `DELETE` removes the file
   and clears `company.logo_ref`.
3. `GET /companies/{id}` returns `logo_url` = the served `/static/uploads/...`
   path when a logo exists, and `null` when it does not.
4. `rg "company_id" src/haandvaerker/api/company_logo.py` shows the endpoint
   takes `company_id` only from `CompanyContextDep`, never from path/body.
5. `ruff check --select E711,E722,F841,F401,B006,B007,S106,RUF100 src/haandvaerker/models/company_config.py src/haandvaerker/api/company_logo.py` → clean.

**Deletions.**
- None expected (greenfield tables + new endpoint). Flagged: this phase is
  pure addition — the cleanup/subtraction lands in Phase 2 where the
  duplicated `.env`-only `is_configured()` logic is collapsed into a single
  resolver, and `email_config_status` stops reading globals.

**Subtraction check.** Can this be achieved by deleting? No — the tables
and upload endpoint are net-new capability. Kept minimal: one combined
`company_config.py` model file (not three) to avoid three-file boilerplate
while preserving three distinct tables; logo endpoint reuses the existing
`/static` mount rather than adding a second StaticFiles mount.

**Net LoC intent.** +120 to +160 (three small table models + schemas, one
upload handler, lifespan mkdir, tests). Flagged as >100: justified by three
tables plus file-upload validation landing together; splitting the tables
from the upload would create a phase whose only deliverable is unused
tables, which is worse for commit-worthiness.

**Rollback.** Revert the commit. No migration to undo — `create_all()` is
additive and unused tables are inert. Delete the `static/uploads/logos/`
directory if created.

### Phase 2: Email + AI config endpoints + service parameter-injection (atomic cutover)

**Goal.** Add `GET/PUT /companies/{id}/email-config` (password write-only,
`password_set` on read), a threadpool-backed `POST .../email-config/test`,
`GET/PUT /companies/{id}/ai-config`, and refactor `smtp_sender.py` /
`email_poller.py` / `local_ai.py` to take credentials as parameters with a
single DB-first/.env-fallback resolver — all in one commit so no
half-migrated state exists.

**Anchors.** `CODE-07`/`CODE-08`/`CONT-09` (import-time global binding),
`CODE-09`/`IMP-04` (local_ai call-time-safe, params easy), `IMP-01`/`IMP-03`
(poll_inbox / send_email signatures), `CONT-07`/`CONT-08`/`IMP-02`
(is_configured + email_config_status go stale), `CONT-01`/`RISK-02`
(password masking), `RISK-01` (SSRF host validation), `RISK-03`/`IMP-06`
(event-loop blocking → run_in_executor + timeout), `RISK-04` (partial
migration is a data-leak bug → atomic cutover), `RISK-07`/`CONT-02`
(AI DB-only per company, no silent global fallback).

**Files.**
```
src/haandvaerker/api/company_config.py            (new — email + ai endpoints + test)
src/haandvaerker/services/config_resolver.py      (new — resolve_email/smtp/ai config, DB-first + logged .env fallback)
src/haandvaerker/services/smtp_sender.py          (params instead of globals)
src/haandvaerker/email_poller.py                  (params instead of globals)
src/haandvaerker/services/local_ai.py             (optional endpoint/model params)
src/haandvaerker/services/invoice_reminder_service.py  (resolve + pass cfg to send_email)
src/haandvaerker/services/wizard_service.py       (resolve + pass cfg to send_email)
src/haandvaerker/api/inbox.py                     (email_config_status + fetch-email use DB resolver)
src/haandvaerker/api/invoice_reminders.py         (smtp_configured flag reads DB resolver)
src/haandvaerker/main.py                           (register company_config router)
tests/test_company_email_ai_config.py             (new)
tests/test_smtp_sender.py / tests/test_email_poller.py  (update for new signatures)
```
This is the largest phase by file count (~9 source files) because it is an
**atomic cutover** — `RISK-04` makes a split here actively dangerous. It
stays one concern: "credentials flow as parameters from per-company config."

**Dependencies.** Phase 1 (tables must exist).

**Acceptance criteria.**
1. `GET /companies/{id}/email-config` response JSON contains
   `password_set` (bool) and contains **no** `password` key:
   `pytest tests/test_company_email_ai_config.py::test_email_config_never_returns_password` passes.
2. `PUT /companies/{id}/email-config` with a password persists it; a
   subsequent GET shows `password_set: true`; PUT with password omitted
   leaves the stored password unchanged (write-only semantics) — covered by
   tests.
3. `POST /companies/{id}/email-config/test` returns within 10 s for an
   unreachable host (assert elapsed < 10 s), and maps connection failure to a
   **structured** error body `{"success": false, "error": "<human-readable message>"}`
   and success to `{"success": true}`. The handler catches only named
   exception classes (never a bare `except Exception: pass`) and logs each
   failure at WARN with `host:port` in context. Catchlist:
   - IMAP: `imaplib.IMAP4.error`, `socket.timeout`, `ConnectionRefusedError`, `OSError`
   - SMTP: `smtplib.SMTPConnectError`, `smtplib.SMTPAuthenticationError`, `socket.timeout`, `ConnectionRefusedError`, `OSError`

   `pytest tests/test_company_email_ai_config.py::test_email_test_times_out_fast` passes,
   and a test asserts the failure response carries `success=false` plus a
   non-empty `error` string.
4. `POST .../email-config/test` with host `127.0.0.1` / `10.x` / `192.168.x`
   → 422 (SSRF guard), no socket opened — test asserts the guard rejects
   before connect.
5. `GET /companies/{id}/ai-config` returns the stored endpoint + models;
   for a company with no AI row, `local_ai.is_enabled(session, company_id)`
   returns `False` (no silent global fallback) —
   `pytest tests/test_company_email_ai_config.py::test_ai_disabled_without_row` passes.
6. `rg "from .config import.*EMAIL_IMAP_HOST" src/haandvaerker/email_poller.py`
   and `rg "from ..config import SMTP_HOST" src/haandvaerker/services/smtp_sender.py`
   return zero hits — services no longer bind globals at import time.
7. `pytest tests/test_smtp_sender.py tests/test_email_poller.py tests/test_wizard.py tests/test_quote_preparations.py tests/test_invoice_reminders.py`
   all pass with the new signatures.
8. `ruff check --select E711,E722,F841,F401,B006,B007,S106,RUF100 <changed src files>` → clean.

**Deletions.**
- `email_poller.py`: module-level `from .config import EMAIL_*` block and
  the global-reading `is_configured()` body (replaced by resolver-driven
  config presence check).
- `smtp_sender.py`: module-level `from ..config import SMTP_*` import and
  the global-reading `is_smtp_configured()` body.
- `inbox.py:email_config_status` global-reading branch (now reads DB
  resolver for the session's company).
- Any now-dead `.env`-only branches in `invoice_reminders.py` smtp flag.

**Subtraction check.** Can this be achieved by deleting? Partly — the
duplicated `is_configured()` / `is_smtp_configured()` global-reading helpers
collapse into one `config_resolver` module, a net structural simplification.
New code (endpoints, SSRF guard, threadpool test) is genuinely additive but
replaces scattered global reads with one resolver, leaving the system better
shaped.

**Net LoC intent.** +180 to +240. Flagged as >100: justified — this is the
mandated atomic cutover (`RISK-04`) covering two endpoints, a connection
test, an SSRF guard, the resolver, and four caller updates. Splitting risks
the half-migrated data-leak state the research explicitly warns against.

**Rollback.** Revert the commit. No schema change (tables from Phase 1 are
unchanged). Services return to reading globals; callers revert. Because the
cutover is atomic, rollback restores a consistent `.env`-only state.

### Phase 3: Prompt config endpoint + wizard DB-first fallback

**Goal.** Add `GET/PUT /companies/{id}/prompts` (validating that a
user-supplied `draft_user` still contains the `{context}` placeholder,
rejecting with 422 if absent), and make the wizard's
`_build_draft_context()` resolve `CompanyPromptConfig` from DB, falling
back deterministically to `prompts.py` defaults when no row exists.

**Anchors.** `CODE-10`/`IMP-05` (wizard imports DRAFT_SYSTEM/USER, fallback
goes in `_build_draft_context`), `CONT-03` (deterministic if/else fallback,
not model-decided), `CODE-13` (inline suggestions prompt — scope
clarification needed, see open questions).

**`{context}` placeholder safety (Iron Law 2 — fail loud at input time).**
A user-saved `draft_user` prompt that drops the `{context}` placeholder
would later raise `KeyError` inside `DRAFT_USER.format(context=...)` at
wizard-call time. We resolve this at **input time, not runtime**: `PUT
/companies/{id}/prompts` validates the `draft_user` field and returns HTTP
422 with a descriptive error (naming the missing `{context}` placeholder)
before the row is ever persisted. This is option (a) from open question 3 —
chosen over a runtime try/except in `_build_draft_context` because failing
at write time prevents a bad prompt from ever reaching the DB, so the wizard
never sees an unformattable prompt. No silent default is introduced.

**Files.**
```
src/haandvaerker/api/company_config.py            (add prompt endpoints)
src/haandvaerker/api/wizard.py                    (_build_draft_context queries DB, falls back to prompts.py)
tests/test_company_prompts.py                     (new)
tests/test_wizard.py                              (add DB-prompt-vs-fallback cases)
```

**Dependencies.** Phase 1 (`CompanyPromptConfig` table). Independent of
Phase 2.

**Acceptance criteria.**
1. `GET /companies/{id}/prompts` returns the stored `draft_system` /
   `draft_user`; `PUT` persists them — `pytest tests/test_company_prompts.py` passes.
2. With a `CompanyPromptConfig` row for company X, the wizard draft uses the
   DB prompt; with no row for company Y, it uses `prompts.py` `DRAFT_SYSTEM`
   / `DRAFT_USER` — `pytest tests/test_wizard.py::test_draft_uses_db_prompt_for_x_fallback_for_y` passes (assert on the prompt strings passed to `local_ai`).
3. `_build_draft_context` contains an explicit `if row:`/`else:` fallback —
   `rg "if row" src/haandvaerker/api/wizard.py` returns at least one hit
   (fallback is Python, not model-driven).
4. `PUT /companies/{id}/prompts` with a `draft_user` value that is missing
   the `{context}` placeholder → HTTP 422 (input-time validation, no row
   persisted) — `pytest tests/test_company_prompts.py::test_draft_user_missing_context_rejected` passes.
5. `ruff check --select E711,E722,F841,F401,B006,B007,S106,RUF100 src/haandvaerker/api/wizard.py src/haandvaerker/api/company_config.py` → clean.

**Deletions.**
- None at file level. The module-level `DRAFT_SYSTEM` / `DRAFT_USER` imports
  in `wizard.py` are **retained** — they are the deterministic fallback per
  `CONT-03`, not dead code. Empty deletions flagged: acceptable here because
  this phase adds a fallback layer on top of an existing constant, by design.

**Subtraction check.** Can this be achieved by deleting? No — DB-prompt
override is net-new behaviour. Kept minimal: the fallback is a two-line
`if row else` in the existing function, not a new prompt-service abstraction.

**Net LoC intent.** +50 to +80.

**Rollback.** Revert the commit. The `CompanyPromptConfig` table (from
Phase 1) remains but is simply unread by the wizard again.

### Phase 4: Settings page + nav entry + /settings route

**Goal.** Ship `static/settings.html` wiring all five sections (master data,
logo, email config, AI config, prompt editor in a folded `<details>`),
add the `/settings` route in `main.py`, and add the "Indstillinger" nav
entry in `nav.js`.

**Anchors.** `IMP-08` (nav SECTIONS array — one new object), `IMP-09`
(settings.html follows wizard.html/export.html standalone pattern + /settings
route), `CONT-01` (UI must show `password_set`, never a password field
prefilled).

**Files.**
```
src/haandvaerker/static/settings.html             (new)
src/haandvaerker/static/nav.js                    (add SECTIONS entry)
src/haandvaerker/main.py                           (/settings HTMLResponse route)
tests/test_settings_page.py                        (new — route + nav-link smoke test)
```

**Dependencies.** Phases 1–3 (all endpoints the page calls must exist).

**Acceptance criteria.**
1. `GET /settings` returns 200 and the HTML contains the five section
   markers — `pytest tests/test_settings_page.py::test_settings_route_serves_page` passes.
2. `static/nav.js` SECTIONS array contains an entry with label
   "Indstillinger" and `defaultHref` "/settings" —
   `rg "Indstillinger" src/haandvaerker/static/nav.js` returns a hit and
   `pytest tests/test_settings_page.py::test_nav_has_settings_link` passes.
3. The prompt editor is inside a folded `<details>` (not `open`) —
   `rg "<details>" src/haandvaerker/static/settings.html` matches and the
   advanced section is not expanded by default.
4. The email-config section renders a `password_set` indicator and a
   write-only password input that is never prefilled from the API. A pytest
   assertion in `tests/test_settings_page.py` extracts the password
   `<input>` markup from the rendered HTML and asserts
   `assert 'value=' not in password_field_html` — confirming the password
   input carries no prefilled `value` attribute —
   `pytest tests/test_settings_page.py::test_password_field_has_no_value` passes.

**Deletions.**
- None (new page + one nav entry). Flagged: frontend addition only.

**Subtraction check.** Can this be achieved by deleting? No — the page is
net-new UI. Kept minimal: one standalone HTML file reusing the established
`nav.js` + fetch pattern (no new JS framework, no build step), one nav
object, one route line.

**Net LoC intent.** +350 to +500 HTML/CSS/JS (per `IMP-09` estimate) + ~15
in main.py/nav.js. Flagged as >100: inherent to a five-section settings
page; this is the only UI phase and cannot be meaningfully subdivided
without shipping a half-wired page.

**Rollback.** Revert the commit. The page and nav entry vanish; all backend
endpoints from Phases 1–3 remain functional via the API directly.

## Cross-cutting concerns

- **Password handling.** Email/SMTP password is write-only across the API:
  accepted on PUT, never echoed on GET (`password_set` bool only), stored
  plaintext in SQLite (accepted known limitation — see out of scope).
  Applies to Phase 2 (API) and Phase 4 (UI never prefills the field).
- **Config resolution policy (DB-first + logged .env fallback).** A single
  `config_resolver` module (Phase 2) owns the decision. The `.env` fallback
  is logged once at INFO on first use per company — legitimate boot/operator
  fallback, not runtime masking. AI is **DB-only per company** (no global
  fallback, `RISK-07`); email/SMTP may fall back to `.env` for the operator's
  own boot config but never cross-routes one company's mail through another's
  credentials (`RISK-04`).
- **SSRF guard.** The shared host-validation helper (reject loopback /
  RFC1918 / link-local) lives in `config_resolver` (Phase 2) and is applied
  by the connection-test endpoint before any socket is opened.
- **Threadpool for blocking I/O.** The connection-test endpoint uses
  `run_in_executor` with a hard timeout (Phase 2) so a slow mail server
  cannot stall the event loop (`RISK-03`, `IMP-06`).
- **Connection-test exception discipline (Iron Law 2).** The Phase 2
  connection-test handler catches only named exception classes — never a
  bare `except Exception: pass`. Failure response schema is
  `{"success": false, "error": "<human-readable message>"}`; success is
  `{"success": true}`. Each caught failure is logged via
  `logger.warning(...)` with `host:port` in the message so operators see
  what failed. Catchlist:
  - IMAP: `imaplib.IMAP4.error`, `socket.timeout`, `ConnectionRefusedError`, `OSError`.
  - SMTP: `smtplib.SMTPConnectError`, `smtplib.SMTPAuthenticationError`, `socket.timeout`, `ConnectionRefusedError`, `OSError`.
- **Ownership scope.** Every config endpoint derives `company_id` solely
  from `CompanyContextDep` (Phases 1–3) — no path/body `company_id`.
- **Tests.** Each phase adds unit/integration tests for its new branches;
  Phase 4 adds a route + nav smoke test. Phase 2 updates existing
  `test_smtp_sender` / `test_email_poller` / `test_wizard` /
  `test_quote_preparations` / `test_invoice_reminders` for the new
  signatures.
- **Migration mechanism.** No `migrations/` SQL file is added — the three
  new tables are standalone and `create_all()` handles them (`CODE-05`,
  `CODE-06`). Local reset path is `reset_demo.bat` (drop + recreate).

## Out of scope

- **SEC-01: unauthenticated `companies.py` endpoints** (`CODE-02`,
  `CONT-06`) — the existing `GET/PATCH/DELETE /companies/{id}` use bare
  `SessionDep`, not `CompanyContextDep`. New config endpoints use
  `CompanyContextDep`; aligning the legacy company endpoints is a **separate
  ticket**, not touched here.
- **Multi-user / roles** — no per-user auth or RBAC on the settings page.
- **Encrypted passwords in DB** — passwords are stored plaintext (known
  limitation; Fernet/SECRET_KEY encryption deferred to a future ticket).
- **The wizard inline suggestions prompt** (`wizard.py:151`, `CODE-13`) is
  **not** brought under `CompanyPromptConfig` unless the user says otherwise
  (open question 1) — only the `DRAFT_SYSTEM` / `DRAFT_USER` draft prompts.
- **Logo retention on company soft-delete** — deactivating a company does
  not delete its logo file from disk (research open question; not handled).
- **Background polling loop changes** — `poll_inbox` is invoked on demand via
  `/inbox/fetch-email`; no scheduled poller exists to re-credential, so the
  "fetch credentials each poll interval" concern reduces to "resolve at each
  `fetch-email` call," which Phase 2 covers.

## Open questions for the user

1. **Suggestions prompt scope.** `CompanyPromptConfig` is planned to cover
   only the wizard `DRAFT_SYSTEM` / `DRAFT_USER` draft prompts. The inline
   suggestions prompt at `wizard.py:151` (`CODE-13`) is currently a
   hardcoded string. Should it also be company-configurable, or stay
   hardcoded for now?
2. **Connection-test error detail.** Should `POST .../email-config/test`
   return the specific failure class to the browser (auth failure vs.
   connection refused), or only `ok` / `fejl`? Detailed messages help the
   user debug but reveal infrastructure detail.
3. **Prompt placeholder safety.** ~~Should `PUT .../prompts` validate that a
   user-supplied `draft_user` still contains `{context}` (422 if missing)?~~
   **Resolved (option a):** Phase 3 now validates `draft_user` at input time
   and returns 422 if the `{context}` placeholder is missing, preventing a
   saved prompt that would crash the wizard's `.format()`. See Phase 3
   "`{context}` placeholder safety". No further input needed unless the user
   prefers a different policy.

## Review invocation

After phase 4 verifies, invoke the `review` skill on
`git diff main...HEAD`. The review skill picks its own reviewer count and
concerns.
