# Plan: Company Settings Drawer + Contact Directory

**Path:** plans/2026-06-06-company-settings-contact-directory.md
**Created:** 2026-06-06
**Research:** research/2026-06-06-company-settings-contact-directory/
**Status:** draft

## Research anchors

All artifacts gitignored under `research/2026-06-06-company-settings-contact-directory/`.
Regenerate via `develop-conductor` if missing.

- `research/2026-06-06-company-settings-contact-directory/brief.md` — synthesised
  brief the user approved. Locks design decisions DP-1 … DP-8 and the 3-phase split.
- `research/2026-06-06-company-settings-contact-directory/researcher-1-code+contract.json`
  — code/contract findings `CODE-01…09`, `CONT-01…06`: Company schema shape, the
  PATCH auth gap, tab-registration touch-points, ContactPerson FK targets, router
  registration pattern, migration approach, conftest fixtures.
- `research/2026-06-06-company-settings-contact-directory/researcher-2-impact-risk.json`
  — impact/risk findings `IMP-01…06`, `RISK-01…07`: test-collision analysis, table
  auto-discovery, LIKE-search performance, logo_ref XSS, loadAll() blocking risk,
  PATCH auth gap (severity HIGH), SQLite FK-enforcement-off orphan risk.
- `research/2026-06-06-company-settings-contact-directory/meta.json` — slug, researcher
  index, plan path.

Phases below cite finding IDs (`CODE-02`, `RISK-02`, `CONT-01`, …) where a decision is
anchored in research evidence.

## Problem

The app needs two operator-facing features built on the existing session system.
(1) **Company settings** — there is no UI to edit the company's own profile (name,
address, phone, email, CVR, logo); clicking the company name in the nav.js topbar
currently does nothing. (2) **Contact directory** — there is no place to record the
people the business works with (customer contacts, employees, suppliers) with search and
links to customers/projects. Building (1) on the existing `PATCH /companies/{id}` exposes
a **pre-existing HIGH-severity authorization gap** (`RISK-02`, `CODE-02`): that endpoint
uses raw `SessionDep` with no session-company cross-check, so any authenticated caller can
edit any company by UUID. A second pre-existing bug blocks the whole effort: `ui.html`'s
`api()` helper omits `credentials:'include'` (`CONT-06` open question), so every
`CompanyContextDep`-protected endpoint the new UI calls would return 401. Both bugs must be
fixed before the features are usable.

## Approach

Three phases, one concern each, ordered so the repo is working and committable after each.
**Phase 1** is the security-and-foundation phase: fix the two pre-existing bugs (PATCH auth
per `DP-1`/`RISK-02`, `api()` credentials per `DP-5`) and add the new `ContactPerson` model
+ hand-written migration (no behaviour exposed yet — table is greenfield). **Phase 2** adds
the `/contact-persons` router (CRUD + LIKE search) following the incumbent `action_items.py`
pattern verbatim (`CODE-09`, `CONT-01…03`), registered in `main.py`. **Phase 3** is the
UI: the company-settings modal in `nav.js` (centered modal reusing `.nav-overlay`/
`.nav-modal-box` per `DP-3`/`CODE-03`) and the lazily-loaded contacts tab in `ui.html`
(`DP-4`, `CONT-06`), both carrying the mandatory contextual-guidance UX (`DP-8`). The
options-researcher did not surface a redesign option; the brief locked extension of the
incumbent router/model/tab patterns, which is the correct call for a small flat app
(`vision §5`).

## Architectural posture

**Incumbent patterns touched, and the verdict: extend, do not redesign.**

1. **Per-resource CompanyContextDep router pattern** (`action_items.py` is the reference,
   `CODE-09`). The new `contact_persons.py` router extends this verbatim: `company_id`
   from `ctx`, list filtered by `ctx.company_id`, get/patch/delete cross-check
   `row.company_id == ctx.company_id` → 403. Phase 1 additionally **brings the lone
   deviant** (`companies.py`, the only one of 34+ routers on raw `SessionDep`, `RISK-02`)
   **back into the pattern**. This is net-positive on all four dimensions:
   - *Separation of concerns*: authorization moves out of "trust the URL" into the same
     session-cookie boundary every other router uses. No new boundary.
   - *Pick-up-ability*: a new engineer reads `action_items.py`, then reads
     `contact_persons.py` and `companies.py`, and finds the identical shape. 10-minute
     pick-up holds.
   - *Extensibility*: the next resource is another copy of the same pattern. Easier, not
     harder.
   - *Security/stability*: **narrows** a trust boundary (closes `RISK-02`). No new failure
     mode introduced.

2. **Hand-written `migrations/NNN_*.sql` with `CREATE TABLE IF NOT EXISTS`** (`CODE-07`,
   `CONT-05`; incumbent is `001_ux_redesign_fields.sql`). The repo deliberately has no
   Alembic (`database.py` comment: "D1=B — no Alembic"). Extending the hand-rolled
   migration directory is consistent; `create_all()` covers fresh/in-memory DBs, the SQL
   file covers existing `haandvaerker.db`. No redesign warranted.

3. **`ui.html` tab system + `nav.js` modal/SECTIONS** (`CODE-03`, `CODE-04`, `CONT-06`).
   Extended in the four documented locations plus the lazy-render path used by
   `erfaringsbank`/`reminders` (`DP-4`, `RISK-07`). The settings modal reuses the existing
   `.nav-overlay`/`.nav-modal-box` CSS rather than inventing a side-drawer in nav.js
   (`DP-3`) — the side-drawer infra lives in ui.html, a different DOM/CSS system, so
   reusing nav's own centered-modal primitive keeps the two systems unblurred.

**Debt accrued.** (a) The CVR edit field cannot pre-populate because GET returns only
`cvr_masked` (`CONT-04`, `vision §6`); `DP-2` accepts this as a UX rule (blank = keep
current) rather than adding an unmasked endpoint — no policy exception, debt is purely a
minor UX wrinkle, not paid down. (b) `tags` as comma-separated string (`RISK-05`) means
search is substring-match, not exact-tag; acceptable at the stated scale, revisit only if a
tag-management feature is requested. (c) ContactPerson FKs are informational only
(`DP-7`, `RISK-03`): SQLite FK enforcement is off and referenced customers/projects may be
soft-deleted, so the router does **not** couple to their active-state — documented, not a
bug. No redesign option was surfaced by research; greenfield table + incumbent patterns is
the right shape.

## Invariants preserved

- **`vision §3` / AGENTS rule 2 (fail loud, never mask).** No `except Exception`, no silent
  defaults. PATCH/save failures surface a Danish error to the user; `RISK-07`'s
  `.catch(() => [])` is used **only** on the dashboard `loadAll()` eager path (a bounded
  startup-style fallback that keeps the dashboard rendering), never on the explicit
  contacts-tab load or on a save.
- **`vision §6` / AGENTS rule 4 (sensitive fields masked).** CVR never leaves the API in
  plaintext: GET keeps `cvr_masked`; the drawer never requests an unmasked value (`DP-2`,
  `CONT-04`). No new endpoint exposes `cvr_number`.
- **`vision §5` (flat structure, register in one place).** New resource = one model file +
  one router file + one `main.py` include + one migration + one test file (`CODE-06`,
  AGENTS §"Adding a new resource").
- **AGENTS rule 4 / `dependencies.py` discipline.** `company_id` is never accepted as a
  body/query field on any new endpoint — always from `CompanyContextDep` (`CONT-01`).
- **Soft-delete consistency (`vision §4` spirit, `DP-7`).** ContactPerson DELETE sets
  `active=False`, matching every other resource; no physical delete.
- **XSS discipline (`RISK-06`, nav.js:7 convention).** User text rendered via
  `textContent`/`esc()`, never `innerHTML`; `logo_ref` rendered as `<img src>` only after a
  `https://`-prefix check (`DP-6`).

## Phases

### Phase 1: Security fixes + ContactPerson model + migration

**Goal.** Close the two pre-existing auth bugs and add the ContactPerson table + migration,
exposing no new user-facing behaviour.

**Anchors.** `CODE-02`, `RISK-02` (PATCH auth gap); `CONT-06`/open-question, `DP-5`
(`api()` credentials); `CODE-05`, `CONT-05`, `IMP-04` (ContactPerson model + FK targets +
auto-discovery); `CODE-07`, `CONT-05` (migration pattern); `CODE-09` (CompanyContextDep
reference); `IMP-01`, `IMP-02` (test-collision analysis).

**Files.**
```
src/haandvaerker/api/companies.py
src/haandvaerker/static/ui.html
src/haandvaerker/models/contact_person.py
migrations/002_contact_persons.sql
tests/test_companies_auth.py
tests/test_model_contact_person.py
```
These are the ONLY paths the implementer may touch in this phase.

**Implementation notes.**
- `companies.py`: change `update_company` (and, for consistency with the 33 other routers
  and to fully close `RISK-02`, the `get`/`delete`/`list` handlers should be reviewed — but
  **only `update_company` and `deactivate_company`/`get_company` that mutate or read a
  single company by id need the cross-check**). Minimum required by the brief: switch
  `update_company` to `CompanyContextDep` and add
  `if company.id != ctx.company_id: raise HTTPException(403, "Adgang nægtet.")` after the
  404 check, mirroring `action_items.py:63`. Use `ctx.session` not `SessionDep`. Note:
  conftest overrides `get_company_context` to a fixed `company_id`, so the cross-company
  test must create a *second* company row and PATCH it (see acceptance criterion 2).
- `ui.html`: the `api()` helper at line 536 — add `credentials: 'include'` to the single
  `fetch(BASE + path)` call. One-line change (`DP-5`).
- `contact_person.py`: `ContactPerson` table + `ContactPersonCreate` /
  `ContactPersonRead` / `ContactPersonUpdate` schemas, following `action_item.py` layout.
  FK strings `"company.id"`, `"customer.id"`, `"project.id"` (`CODE-05`). `company_id`
  required + `index=True`; `customer_id`/`project_id` optional + `index=True`. Fields per
  brief: `name` (required, ≤200), `title`/`phone`/`email`/`tags`/`comment` optional,
  `contact_type` str default `"other"` (≤20), `active` bool default True, `created_at` UTC.
  `ContactPersonCreate` excludes `company_id` (`CONT-01`). `ContactPersonRead` exposes all
  stored fields (no masking needed — no sensitive field on this model). `ContactPersonUpdate`
  all-Optional incl. `active`.
- `migrations/002_contact_persons.sql`: single `CREATE TABLE IF NOT EXISTS contactperson`
  (lowercase, `CODE-05`) with header comment matching `001_*.sql` style; columns mirror the
  model; `active INTEGER NOT NULL DEFAULT 1`; FK `REFERENCES` clauses informational
  (SQLite FK enforcement off, `RISK-03`).

**Dependencies.** None.

**Acceptance criteria.**
1. `python -m pytest tests/ -q` passes all existing tests plus the two new files
   (≥743 + new).
2. `python -m pytest tests/test_companies_auth.py -v` passes a test that: creates a second
   company directly in the session, sets the session context to company A, PATCHes company
   B's id, and asserts `403` with Danish detail `"Adgang nægtet."`.
3. `python -c "from haandvaerker.models.contact_person import ContactPerson, ContactPersonCreate, ContactPersonRead, ContactPersonUpdate; print('ok')"` exits 0.
4. `(Select-String -Path migrations/002_contact_persons.sql -Pattern 'CREATE TABLE' -AllMatches).Matches.Count` equals 1 (PowerShell), or `grep -c "CREATE TABLE" migrations/002_contact_persons.sql` returns 1 (bash).
5. `Select-String -Path src/haandvaerker/static/ui.html -Pattern "credentials: ?'include'"` finds the string inside the `api()` function (read lines 535-540 to confirm it is on the `api()` fetch, not elsewhere).

**Deletions.**
- `src/haandvaerker/api/companies.py`: removal of the raw `SessionDep`-based authorization
  on `update_company` (the `SessionDep` import/alias stays if still used by other handlers;
  if `update_company` was its last user, delete the unused `SessionDep` alias and the
  `get_session` import — verify with ruff F401).
- No other deletions.

**Subtraction check.** Cannot be achieved by pure deletion — a new table and new auth check
are genuine additions. But the PATCH fix is a *replacement* (swap masking-prone `SessionDep`
for `CompanyContextDep`), net near-zero on that file, and removes an attack surface. Net LoC
estimate: ~+90 (model ~55, migration ~15, two small test files ~60, companies.py ≈ 0 net).

**Rollback.** `git revert` the commit. The migration is `CREATE TABLE IF NOT EXISTS` against
a not-yet-referenced table — dropping `contactperson` (dev only) or reverting leaves existing
data untouched. No column changes to existing tables.

---

### Phase 2: Contact directory API + tests

**Goal.** Add the `/contact-persons` CRUD + search router and register it, with full test
coverage including cross-company isolation.

**Anchors.** `CODE-06` (router registration pattern), `CODE-09` (CompanyContextDep
get/patch/delete cross-check), `CONT-01` (POST body excludes company_id), `CONT-02`
(GET filters: q / customer_id / project_id / active_only), `CONT-03` (PATCH all-Optional +
active), `RISK-04` (parameterized LIKE — no injection), `RISK-05` (tags substring-match
semantics), `IMP-04` (table auto-discovery requires registration in main.py), `IMP-05`
(no index needed at scale).

**Files.**
```
src/haandvaerker/api/contact_persons.py
src/haandvaerker/main.py
tests/test_contact_persons.py
```
These are the ONLY paths the implementer may touch in this phase.

**Implementation notes.**
- `contact_persons.py`: `APIRouter(prefix="/contact-persons", tags=["contact-persons"])`.
  Five endpoints mirroring `action_items.py`:
  - `POST /` → 201, `company_id` from `ctx`, `id = str(uuid.uuid4())`,
    `**data.model_dump()`.
  - `GET /` → list filtered by `ctx.company_id`; query params `q: Optional[str]`,
    `customer_id: Optional[str]`, `project_id: Optional[str]`, `active_only: bool = True`.
    Search: `from sqlmodel import or_, col`; when `q` set, add
    `.where(or_(col(ContactPerson.name).contains(q), col(ContactPerson.phone).contains(q),
    col(ContactPerson.email).contains(q), col(ContactPerson.tags).contains(q)))`.
    `.contains()` emits a bound-parameter LIKE — no f-string SQL (`RISK-04`). Substring
    semantics on tags are accepted (`RISK-05`).
  - `GET /{id}`, `PATCH /{id}`, `DELETE /{id}` → 404 if missing, then
    `if row.company_id != ctx.company_id: raise HTTPException(403, "Adgang nægtet.")`.
    DELETE is soft (`active = False`, `DP-7`). No coupling to customer/project active-state
    (`RISK-03`, `DP-7`).
  - No `except Exception`; no silent defaults.
- `main.py`: `from .api.contact_persons import router as contact_persons_router` and
  `app.include_router(contact_persons_router)` alongside the others (`CODE-06`). This import
  is what makes `create_all()` discover the table in tests (`IMP-04`).
- `tests/test_contact_persons.py`: cover create, list, search by `q` (positive + negative
  match), filter by `customer_id`, filter by `project_id`, get, patch, delete (soft —
  assert `active` False and excluded from default list), and cross-company isolation. For
  the 403 isolation test, follow the `IMP-04`/conftest note: create a contact owned by a
  *different* `company_id` directly in the session, then GET/PATCH/DELETE it via the client
  (whose ctx is fixed to the conftest company) and assert 403.

**Dependencies.** Phase 1 (model + migration must exist).

**Acceptance criteria.**
1. `python -m pytest tests/test_contact_persons.py -v` passes.
2. `python -m pytest tests/ -q` passes all tests.
3. A test asserts `GET /contact-persons/?q=lars` returns only contacts whose
   name/phone/email/tags contain `lars`, and excludes a non-matching control contact.
4. A test asserts `GET /contact-persons/{id}` for a contact owned by another company returns
   `403` with detail `"Adgang nægtet."`.
5. `Select-String -Path src/haandvaerker/main.py -Pattern "contact_persons_router"` returns
   two hits (import + include).

**Deletions.**
- None. (Flagged: this is a pure-addition phase. Justified — it adds a genuinely new
  resource. The plan's cleanup/removal work lives in Phase 1, which removes the
  `RISK-02` auth gap and any now-unused `companies.py` import.)

**Subtraction check.** Cannot subtract — a new resource router is required new behaviour.
Minimised by reusing `action_items.py` structure verbatim (no new abstraction, one caller
each). Net LoC estimate: ~+120 (router ~75, main.py +2, tests ~120 → flagged > 100; justified
as required CRUD + isolation coverage for a new resource, mostly test lines).

**Rollback.** `git revert` the commit; remove the two `main.py` lines. The table from Phase 1
remains but is simply unused — no data loss.

---

### Phase 3: UI — company settings drawer + contacts tab

**Goal.** Wire the company-settings modal into the nav.js topbar and add the lazily-loaded
contacts tab with full contextual-guidance UX, with no silent failures.

**Anchors.** `CODE-03` (nav.js company-name span + `.nav-overlay`/`.nav-modal-box` reuse),
`RISK-01` (refresh `#nav-company-name` + `#co-name` after PATCH), `CONT-04`/`DP-2` (CVR
masked placeholder, blank = keep), `DP-6`/`RISK-06` (logo_ref https:// validation before
img.src), `CODE-04`/`CONT-06`/`IMP-03` (four ui.html tab touch-points + nav.js SECTIONS),
`DP-4`/`RISK-07` (lazy load on first `showTab('contacts')`), `DP-8` (contextual guidance).

**Files.**
```
src/haandvaerker/static/nav.js
src/haandvaerker/static/ui.html
```
These are the ONLY paths the implementer may touch in this phase.

**Implementation notes — settings modal (nav.js).**
- Attach a click handler to the `#nav-company-name` span (`CODE-03`). On click: read the
  company id from the same source `initNav()` uses (the `/session/current` payload — store
  the id when fetched), `GET /companies/{id}` to pre-populate, build a `.nav-overlay` +
  `.nav-modal-box` modal (same primitive as `openSwitchModal`, `CODE-03`).
- Fields: Navn, Adresse, Telefon, E-mail, CVR (input `placeholder` = the masked value from
  GET, e.g. `****1234`; inline grey hint "Lad CVR-feltet tomt for at beholde nuværende
  CVR"; `DP-2`), Logo URL (inline hint "Indsæt en URL til virksomhedens logo
  (https://...)"; `DP-6`).
- Save: build the PATCH body from non-empty fields only; **omit CVR if the field is blank**
  (`DP-2`) so the masked placeholder never overwrites the stored value. `PATCH
  /companies/{id}` via `fetch(..., {credentials:'include'})`. On success: update
  `#nav-company-name` (nav.js) and `#co-name` (ui.html, if present) via `textContent`
  (`RISK-01`), close modal. On failure: render a Danish error message below the form
  (`vision §3` — no silent swallow, no `except`-style empty catch that hides the error).
- logo_ref render (if shown anywhere as an image): only set `img.src` when the value starts
  with `https://`; otherwise show a placeholder icon (`DP-6`, `RISK-06`). Never `innerHTML`.

**Implementation notes — contacts tab (ui.html + nav.js SECTIONS).**
- Four ui.html locations (`CONT-06`, `CODE-04`): (1) add `'contacts'` to the `showTab()`
  array at ~line 592; (2) add `<div class='tab' data-tab='contacts'>Kontakter</div>` to the
  hidden `.tabs` bar; (3) add `<div id='tab-contacts' style='display:none'></div>` to the
  tab-content block; (4) add `contacts: 'Kontakter'` to `TAB_LABELS`.
- nav.js SECTIONS: add `{ label: 'Kontakter', href: '/ui?tab=contacts' }` under the
  Projekter section's subs (`CONT-06`, `IMP-03`).
- **Lazy load (`DP-4`, `RISK-07`)**: do NOT add contacts to `loadAll()`'s `Promise.all`.
  Instead, on the first `showTab('contacts')` call, fetch
  `api('/contact-persons/?active_only=true')` and render. Guard with a "loaded once" flag.
  If this explicit fetch fails, surface the error in the tab (fail loud, `vision §3`) — do
  NOT use `.catch(() => [])` here (that masking pattern is reserved for the dashboard eager
  path only, `RISK-07`).
- Contextual guidance (`DP-8`):
  - Empty state: "Du har ingen kontakter endnu. Tilføj din første kontaktperson og hold styr
    på hvem du arbejder med." + prominent `[+ Tilføj kontaktperson]` button.
  - List rows: name, title, phone as click-to-call `tel:` link, email, type-badge
    (`contact_type`), tags, linked customer/project. All user text via `esc()`/`textContent`.
  - Search: input with 300 ms debounce → `GET /contact-persons/?q=…` live filter.
  - `[+ Ny kontakt]` button top-right; create/edit modal with fields for all ContactPerson
    fields.
  - Post-create banner: "Kontakten er gemt! Tilknyt til en sag →" fading after 4 s.

**Dependencies.** Phase 1 (`api()` credentials fix, Company schema) and Phase 2
(`/contact-persons` endpoints) must be merged.

**Acceptance criteria.** (UI — verified by reading the diff + manual smoke; the harness
cannot click. State each as a concrete file-state or behaviour check.)
1. `Select-String -Path src/haandvaerker/static/nav.js -Pattern "nav-company-name"` shows a
   click/event handler is attached (read the surrounding block to confirm it opens an
   overlay).
2. The nav.js save handler, on PATCH success, calls `textContent` updates on both
   `#nav-company-name` and `#co-name` (verify by reading the save handler).
3. `Select-String -Path src/haandvaerker/static/ui.html -Pattern "Du har ingen kontakter endnu"`
   returns 1 hit (empty-state guidance present).
4. `Select-String -Path src/haandvaerker/static/ui.html -Pattern "contacts"` confirms all
   four touch-points (showTab array, `data-tab='contacts'`, `id='tab-contacts'`,
   `TAB_LABELS`) — read the four sites.
5. `python -m pytest tests/ -q` passes (no Python regressions; UI files are static).
6. The logo render path guards on `https://` before assigning `img.src` (verify by reading
   the render code) and uses `textContent`/`esc()` for all user-supplied contact text
   (`RISK-06`, `DP-6`).
7. The contacts-tab lazy load does NOT appear inside `loadAll()`'s `Promise.all`
   (`Select-String` the `loadAll` block shows no `/contact-persons`); the explicit tab load
   has no `.catch(() => [])` masking (verify by reading the load function).

**Deletions.**
- None expected in static UI files (additive feature surface). If the implementer finds a
  dead handler or commented-out block adjacent to the edited regions, remove it (per
  code-minimalism §1/low). Flagged: pure-addition UI phase — acceptable because the
  removal/repair work is concentrated in Phase 1.

**Subtraction check.** Cannot subtract — these are new UI surfaces (modal + tab) the user
explicitly requested. Minimised by reusing the existing `.nav-overlay`/`.nav-modal-box`
primitive (no new modal framework) and the existing lazy-render tab pattern (no new tab
machinery). Net LoC estimate: ~+220 across two large static files (flagged > 100; justified
as two genuinely new UI features with mandated guidance UX, concentrated in static HTML/JS
not application logic).

**Rollback.** `git revert` the commit. Static files only — no schema, no API change; reverting
restores the prior UI with zero data impact.

## Cross-cutting concerns

- **Authorization.** Every new endpoint (Phase 2) and the fixed PATCH (Phase 1) use
  `CompanyContextDep` and the `row.company_id != ctx.company_id → 403 "Adgang nægtet."`
  cross-check (`CODE-09`). `company_id` is never a body/query field (`CONT-01`,
  `dependencies.py` discipline).
- **Danish, fail-loud errors.** All new HTTP errors and UI save/load failures produce Danish
  messages; no `except Exception`, no silent defaults (`vision §3`, AGENTS rule 2). The only
  permitted `.catch(() => [])` is the pre-existing dashboard eager-load fallback, never on
  the explicit contacts load or any save (`RISK-07`).
- **Sensitive data.** CVR stays masked on every GET; the drawer never fetches plaintext and
  omits CVR from PATCH when blank (`vision §6`, `DP-2`, `CONT-04`).
- **XSS.** `logo_ref` rendered as `img.src` only after `https://` check; all user text via
  `textContent`/`esc()` (`RISK-06`, `DP-6`).
- **Migration discipline.** Phase 1 ships `migrations/002_contact_persons.sql`
  (`CREATE TABLE IF NOT EXISTS`); existing `haandvaerker.db` users must run it manually
  (header comment states this, matching `001_*.sql`). Fresh DBs and in-memory tests get the
  table from `create_all()` once the router is registered (`IMP-04`, Phase 2).
- **Tests.** Phase 1 adds model + auth tests; Phase 2 adds full CRUD/search/isolation tests;
  Phase 3 relies on the existing suite passing (static files) plus diff-read verification.
- **Test fragility note (`IMP-02`).** `test_quote_acceptance.py:74` hard-codes
  `'Test Firma AS'`. In-memory isolation protects it today; do not introduce any test that
  shares session state and PATCHes the conftest company name.

## Out of scope

- **No unmasked CVR endpoint.** `DP-2`/`CONT-04` — CVR pre-population is intentionally not
  supported; no `vision §6` exception is requested.
- **No file-upload for logo.** `logo_ref` stays a URL/path string; no multipart, no S3/local
  storage (`IMP-06`, `vision` "Bilag … storage er ekstern").
- **No tag-management / exact-tag indexing.** Tags remain a comma-separated string with
  substring search (`RISK-05`).
- **No FK active-state coupling.** ContactPerson links to customers/projects are
  informational; the router does not hide contacts whose linked customer/project is
  soft-deleted (`DP-7`, `RISK-03`).
- **No broader companies.py refactor.** Only the single-company auth path is fixed; the
  list/create endpoints' behaviour is unchanged beyond the `RISK-02` cross-check on
  single-company mutation/read.
- **No SQLite PRAGMA foreign_keys change.** Enabling DB-level FK enforcement (`RISK-03`) is a
  repo-wide decision, not part of this slice.
- **No PWA/offline handling** for the new tab.

## Open questions for the user

None blocking — all design decisions (DP-1 … DP-8) are locked in `brief.md`. One advisory
note for the user to confirm at plan approval, not a blocker:

1. Phase 1 fixes the `RISK-02` cross-check on `update_company` (and `get`/`delete` single-
   company paths for consistency). Confirm you do NOT also want `list_companies`/
   `create_company` reshaped in this slice — the plan deliberately leaves company creation/
   listing as-is (a company picker must list across companies before a session exists).

## Review invocation

After Phase 3 verifies PASS, invoke the `review` skill on `git diff main...HEAD`. The review
skill picks its own reviewer count and concerns. Plan persisted — after all phases verify
PASS, the merge gate is the `review` skill on the full diff.
