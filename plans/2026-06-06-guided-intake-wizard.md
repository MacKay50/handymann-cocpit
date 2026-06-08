# Plan: Guided Intake Wizard (Plan C)

**Path:** plans/2026-06-06-guided-intake-wizard.md
**Created:** 2026-06-06
**Research:** research/2026-06-06-guided-intake-wizard/
**Status:** approved (phase-1-revised)

## Research anchors

These artifacts under `research/2026-06-06-guided-intake-wizard/` are
gitignored â€” regenerate with `develop-conductor` if missing. Phases
below cite specific finding IDs.

- `research/2026-06-06-guided-intake-wizard/brief.md` â€” synthesised
  brief; all five design points (DP-1â€¦DP-5) locked by the user as
  A1, B1+B2, C1, D2, E3.
- `research/2026-06-06-guided-intake-wizard/researcher-1-code-contract.json`
  â€” `convert-to-flow` shape (CODE-01, CONT-08), absence of a
  `POST /quote-preparations/` creation path (CODE-09, CONT-04),
  `smtp_sender.send_email` plain-text contract (CODE-03, CONT-09),
  `chat_completion` availability (CODE-04, CODE-10), CVR/DAWA gap
  (CODE-08, CONT-07), cross-company leak in `similarity_search`
  (CONT-10), entity field contracts (CONT-01, CONT-02, CONT-03,
  CONT-05).
- `research/2026-06-06-guided-intake-wizard/researcher-2-impact-risk.json`
  â€” 30-file test blast radius (IMPACT-01), convert-to-flow coverage
  and idempotency (IMPACT-02, RISK-08), `CompanyContextDep` is
  authoritative and already wired into the test harness (IMPACT-03,
  IMPACT-06), no wizard page exists (IMPACT-05), partial-creation /
  single-commit atomicity (RISK-01), graceful-degrade precedent for
  external/email/AI failures (RISK-02, RISK-03, RISK-05), duplicate
  customer risk (RISK-06), minimum-viable field set (RISK-07).
- `research/2026-06-06-guided-intake-wizard/researcher-3-options.json`
  â€” the four option families and locked picks: OPT-Aâ†’A1 (backend
  CVR lookup), OPT-Bâ†’B1+B2 (keyword baseline + opt-in AI), OPT-Câ†’C1
  (dedicated `/wizard` page), OPT-Dâ†’D2 (editable email-preview step).
- `research/2026-06-06-guided-intake-wizard/meta.json` â€” research run
  metadata.

## Problem

The platform has all the back-end plumbing to turn a phone enquiry
into a Customer + Enquiry + Project + Quote (`convert-to-flow`,
`CompanyContextDep`, SMTP sender, experience-bank search, local AI),
but no path that lets an operator drive that flow live during a call
without leaving the page or losing state. There is no way to create a
`QuotePreparation` draft except from an existing `InboxMessage`
(CODE-09, CONT-04), the enquiry source is hardcoded to `email`
(CONT-08), there is no CVR/address lookup (CODE-08), no confirmation
email template (CODE-03), and no multi-step UI (CODE-07). We are
building a **Guided Intake Wizard** â€” a fullscreen 4-step flow at
`/wizard` backed by a server-side `QuotePreparation` draft â€” so an
operator can complete customerâ†’projectâ†’quoteâ†’confirmation in one
sitting, never blocked mid-call (minimum viable = customer name + a
task description, RISK-07).

## Approach

We follow the locked design points exactly. Architecture is **E3**:
the wizard creates a `QuotePreparation` draft on Step 1 via a new
`POST /quote-preparations/` endpoint, PATCHes it across Steps 2â€“3 via
the **existing** `PATCH /quote-preparations/{id}`, and finalises on
Step 4 by calling the **existing** `convert-to-flow` extended with an
optional `source` parameter (CONT-08). CVR enrichment is **A1**: a
new `POST /wizard/cvr-lookup` proxy calling `cvrapi.dk` via stdlib
`urllib.request`, degrading to empty fields on any failure (RISK-02
graceful-degrade precedent). Suggestions are **B1+B2**: a new
`POST /wizard/suggestions` that always runs the deterministic
`keyword_search()` and additionally runs `chat_completion()` only
when `local_ai.is_enabled()` is true (RISK-05). Email is **D2**: an
editable subject/body preview step; if SMTP is unconfigured the step
shows a persistent visible notice and the wizard still completes
(Iron Law 2 â€” explicit, not silent). UI is **C1**: a new
`wizard.html` static file served by a new `GET /wizard` route, with a
sidebar entry in `nav.js`. The phase decomposition isolates one
concern per phase: (1) the creation + lookup + email-template
back-end foundation, (2) the suggestion endpoint plus the CONT-10
data-leak fix, (3) the convert-to-flow `source`/email extension, (4)
the frontend. Each phase leaves the repo green and committable.

## Architectural posture

**Extending**, not redesigning. The incumbent pattern is the
**`QuotePreparation`-as-draft â†’ `convert-to-flow` finaliser** pattern
already proven for the inbox path (CODE-01, IMPACT-02). The
options-researcher surfaced a redesign alternative (DP-5 / E2: a new
`POST /guided-intake` endpoint that calls individual create-endpoints
sequentially and owns dedup). The user locked **E3 (extend)** over E2
(redesign). Extension wins on net for four reasons mapped to the
architect dimensions:

- **Separation of concerns** â€” E3 keeps a single atomic
  entity-creation site (`convert-to-flow`, one `session.commit()`,
  RISK-01) rather than spawning a second multi-entity creation path
  that would duplicate the transactional discipline and drift from
  it. The wizard's new code is confined to thin HTTP adapters
  (creation endpoint, CVR proxy, suggestions endpoint) plus one
  service module (`wizard_service.py`) for template/email policy â€”
  matching AGENTS.md "policy in its own function, not inline".
- **Pick-up-ability** â€” a new engineer already understanding the
  inboxâ†’preparationâ†’convert flow finds the wizard is the same flow
  with a different front door. `POST /quote-preparations/` sits
  beside the existing `from-inbox` creator in the same router file;
  `wizard.html` is a sibling of the seven existing static pages.
- **Extensibility** â€” adding `source` as a parameter (rather than a
  second endpoint) means any future intake channel (walk-in,
  website) reuses the same finaliser by passing a different enum
  value. The draft layer also gives browser-close recovery for free
  (RISK-04).
- **Security / stability** â€” every new endpoint takes `company_id`
  from `CompanyContextDep` only (IMPACT-03), widening no trust
  boundary. Two new outbound/failure modes are introduced (CVR HTTP
  call, confirmation email) and both are explicitly bounded: CVR
  degrades to empty fields, email follows the invoice-reminder
  "save the record, surface the error, never roll back" precedent
  (RISK-03). The plan also *closes* an existing hole â€” the CONT-10
  cross-company leak in `similarity_search` â€” in Phase 2.

**Debt accrued by extending:** (a) `convert-to-flow` grows an
optional `source` and optional email params, nudging it toward a
god-endpoint; the pay-down trigger is "when a third intake channel or
a second email type appears, extract a `flow_finaliser` service from
the endpoint body." (b) `HistoricalOffer` has no structured
line-item list, so B1 suggested lines are synthesised heuristically
from flat fields (DP-2); pay-down trigger is "when suggestion quality
complaints arrive, add a structured `line_items` column and a
migration." Both are recorded here and in Out-of-scope, not silently
carried.

## Invariants preserved

- **`company_id` only from the signed session** (AGENTS.md design
  rule, IMPACT-03) â€” every new endpoint uses `CompanyContextDep`;
  none accepts `company_id` in query or body. The CONT-10 fix brings
  `similarity_search` into compliance with the company-scoping
  invariant that `keyword_search` already honours.
- **Errors are visible; no masking fallbacks** (vision.md Â§3, Iron
  Law 2) â€” CVR failure returns empty fields with an explicit
  `looked_up: false` flag (a degraded *result*, not a masked value);
  email failure returns `email_sent: false` with the error detail;
  unconfigured SMTP shows a persistent UI notice. No
  `.get("x", 0)`-style substitution on business fields.
- **Sensitive fields stay masked** (vision.md Â§6, AGENTS.md rule 4) â€”
  the wizard never returns full `cvr_number` from any GET; CVR typed
  into the lookup is request input, and stored CVR continues to read
  back via `cvr_masked`.
- **Kunden er omdrejningspunktet** (vision.md Â§1) â€” the wizard still
  routes all created data through Customerâ†’Projectâ†’Quote via the
  existing finaliser; no resource is created without its project link.
- **No ORM objects in responses** (AGENTS.md rule 7) â€” new endpoints
  return Pydantic response models only.
- **UUID idempotency / single-commit atomicity** (AGENTS.md rule 6,
  RISK-01, RISK-08) â€” the wizard reuses `convert-to-flow`'s existing
  `status==converted` idempotency guard; no new atomicity logic.

## Phases

### Phase 1: Back-end foundation â€” direct draft creation, CVR lookup, email template

**Goal.** Add the back-end entry points the wizard needs that do not
touch `convert-to-flow`: direct `QuotePreparation` creation, a CVR
proxy, and the confirmation-email template/service â€” each behind
`CompanyContextDep`, each graceful on failure.

**Net LoC intent:** ~180 net lines (wizard.py ~60, wizard_service.py
~50, QuotePreparationCreate ~15, tests ~55). Justified: the entire
wizard API foundation is genuinely new behaviour with no existing
equivalent to extend or subtract (CODE-08, CONT-04, CODE-03 confirm
absence).

**Anchors.** `CODE-09`, `CONT-04` (no creation path / need a
`QuotePreparationCreate` model), `CONT-01`/`CONT-05` (minimum field
set), `CODE-08`/`CONT-07`/`RISK-02` (no CVR lookup; graceful-degrade
precedent), `CODE-03`/`CONT-09` (plain-text email, no template),
`OPT-A`â†’A1, `RISK-07` (minimum viable = name + task).

**Files.**
```
src/haandvaerker/models/quote_preparation.py
src/haandvaerker/api/quote_preparations.py
src/haandvaerker/api/wizard.py
src/haandvaerker/services/wizard_service.py
src/haandvaerker/main.py
tests/test_quote_preparations.py
tests/test_wizard.py
```

These are the ONLY paths the implementer may touch in this phase.
`main.py` is touched solely to register the new `wizard_router`.

**Dependencies.** None.

**Acceptance criteria.**
1. `pytest tests/test_wizard.py tests/test_quote_preparations.py`
   passes, including new tests: (a) `POST /quote-preparations/` with
   only `{"customer_name": "X"}` returns 201 and a `QuotePreparationRead`
   with `inbox_message_id == null` and `status == "draft"`; (b) POST
   with missing `customer_name` returns 422 (field required, min_length=1);
   POST with empty string `customer_name: ""` also returns 422; (c) `POST /wizard/cvr-lookup` with a stubbed
   `cvrapi.dk` success returns `{name, address, phone, looked_up: true}`;
   (d) with the network call stubbed to raise, the same endpoint
   returns 200 with empty `name`/`address`/`phone` and
   `looked_up: false` â€” never 4xx/5xx.
2. Backward compatibility preserved: the existing
   `PATCH /quote-preparations/{id}` and
   `POST /quote-preparations/from-inbox/{id}` paths still behave
   unchanged â€” verified by tests in `tests/test_quote_preparations.py`:
   (a) `from-inbox` against an existing `InboxMessage` still returns a
   `QuotePreparationRead` with the originating `inbox_message_id`
   populated (non-null); (b) `PATCH /quote-preparations/{id}` still
   updates a draft whether it was created `from-inbox` (non-null
   `inbox_message_id`) or via the new direct path
   (`inbox_message_id == null`) â€” the same handler serves both.
3. `rg "QuotePreparationCreate" src/haandvaerker/models/quote_preparation.py`
   returns a class definition with `customer_name: Optional[str]` and
   no `company_id` field.
4. `rg "company_id" src/haandvaerker/api/wizard.py` shows `company_id`
   sourced only from `ctx.company_id`, never from a request body/query
   parameter.
5. `ruff check --select E711,E722,F841,F401,B006,B007,S106,RUF100 src/haandvaerker/api/wizard.py src/haandvaerker/services/wizard_service.py`
   reports zero findings; `mypy src/haandvaerker/` passes.
6. `wizard_service.build_confirmation_email(customer_name, project_title, company_name)`
   returns a `(subject, body)` tuple of plain strings (covered by a
   unit test in `tests/test_wizard.py`).

**Deletions.** None. (See Subtraction check â€” this is genuine new
behaviour with no existing redundant code to remove; the residual-
cleanup work lands in Phase 3 where `source=email` becomes a default.)

**Subtraction check.** Can the goal be reached by deleting instead of
adding? No â€” there is no existing direct-creation, CVR, or
email-template code to subtract (CODE-08, CONT-04, CODE-03 all
confirm absence). We minimise the addition per ladder rung 5:
`QuotePreparationCreate` reuses the existing model's fields rather
than introducing a parallel schema; the CVR proxy uses stdlib
`urllib.request` (no new dependency, per OPT-A) and the existing
`local_ai.py` "return-None / log-WARNING on URLError" shape as its
graceful-degrade template; `build_confirmation_email` is a plain
function, not a template engine.

**Rollback.** Revert this commit. No schema migration (the
`QuotePreparation` table already has nullable `inbox_message_id`,
CODE-09) â€” `QuotePreparationCreate` is a Pydantic request model only,
so there is no DB change to unwind.

### Phase 2: Experience-bank suggestion endpoint + cross-company leak fix

**Goal.** Add `POST /wizard/suggestions` (keyword baseline always,
AI opt-in) and close the CONT-10 cross-company data leak in
`similarity_search` so the suggestion path is company-safe.

**Net LoC intent:** ~90 net lines (wizard.py suggestion endpoint ~40,
offer_search.py company-scope change roughly net-neutral â€” narrows an
existing query rather than adding one, ~5, tests ~45). Justified: the
endpoint reuses existing `keyword_search`/`chat_completion` rather than
re-implementing search, and the CONT-10 fix is a scope *narrowing*, not
an addition â€” the leaky path is deleted, holding net LoC low.

**Anchors.** `OPT-B`â†’B1+B2, `CODE-02` (search lives in
`offer_search`/`historical_comparisons`), `CODE-04`/`CODE-10`/`RISK-05`
(`chat_completion` available, unused, returns None on failure;
`is_enabled()` gate), `CONT-10` (cross-company leak â€” `similarity_search`
has no `company_id` filter), `DP-2` (no structured line items â€”
synthesise heuristically).

**Files.**
```
src/haandvaerker/services/offer_search.py
src/haandvaerker/api/historical_comparisons.py
src/haandvaerker/api/wizard.py
tests/test_wizard.py
tests/test_offer_search.py
tests/test_historical_comparisons.py
```

`historical_comparisons.py` is touched only because it is the
existing caller of `similarity_search` (CONT-10, line 76) and must be
updated to pass the new `company_id` argument.

**Dependencies.** Phase 1 (the `wizard_router` and `wizard.py` module
must exist).

**Acceptance criteria.**
1. `pytest tests/test_wizard.py tests/test_offer_search.py tests/test_historical_comparisons.py`
   passes, including: (a) `POST /wizard/suggestions` with
   `{"work_type": "maling"}` returns a `suggested_lines` list derived
   from `keyword_search` (deterministic, no AI) even when
   `local_ai.is_enabled()` is false; (b) a new
   `test_similarity_search_company_scoped` asserts that an offer
   belonging to company B is **not** returned when searching as
   company A.
2. `similarity_search` signature includes a required `company_id: str`
   parameter â€” verify: `rg "def similarity_search" src/haandvaerker/services/offer_search.py`
   shows `company_id` in the signature; `rg "similarity_search\(" src/haandvaerker`
   shows every call site passes it.
3. `POST /wizard/suggestions` response distinguishes source: response
   includes `ai_used: bool` reflecting whether `chat_completion` ran
   (false when `is_enabled()` is false). Covered by a test that
   monkeypatches `is_enabled` both ways.
4. `ruff check --select E711,E722,F841,F401,B006,B007,S106,RUF100 src/haandvaerker/services/offer_search.py src/haandvaerker/api/wizard.py`
   reports zero findings; `mypy src/haandvaerker/` passes.

**Deletions.**
- The unfiltered cross-company chunk fetch behaviour in
  `offer_search.similarity_search` (`offer_search.py:90-92`) â€” the
  query that pulls **all** companies' chunks is removed and replaced
  by a `company_id`-scoped query. This is a same-concept correction,
  not pure addition: the leaky path is deleted.

**Subtraction check.** Can the goal be reached by deleting instead of
adding? Partially â€” the CONT-10 fix is achieved by *narrowing* an
over-broad query (a subtraction of scope, ladder rung 3). The
suggestion endpoint itself is genuine new behaviour, but it is
minimised: it calls the existing `keyword_search` rather than
re-implementing search, and AI is an additive branch gated behind the
existing `is_enabled()` â€” no new AI plumbing (CODE-04). Per DP-2 we do
not add a `line_items` column; lines are synthesised from existing
flat fields, avoiding a migration.

**Rollback.** Revert this commit. The `similarity_search` signature
change and its single caller revert together; no schema migration.

### Phase 3: Extend convert-to-flow with `source` + optional confirmation email

**Goal.** Let the finaliser record `source=phone` and optionally send
the confirmation email after a successful commit â€” without ever
rolling back created entities on email failure.

**Net LoC intent:** ~100 net lines (quote_preparations.py optional
request model + post-commit send block ~35, wizard_service.py send
wrapper ~20, tests ~45). Justified: behaviour is genuinely new
(channel `source` + post-commit email) but minimised by *extending the
existing finaliser* (E3) â€” an optional parameter and one
`if send_email:` block, not a parallel code path; failure handling
reuses the invoice-reminder shape (RISK-03) rather than inventing one.

**Anchors.** `CODE-01` (convert-to-flow shape), `CONT-08` (hardcoded
`source=email`), `CODE-05` (`EnquirySource.phone` is a valid enum),
`CODE-03`/`CONT-09` (`send_email` plain-text contract), `RISK-03`
(invoice-reminder precedent: save record, mark failed, never roll
back), `IMPACT-02`/`RISK-08` (idempotency must be preserved),
`IMPACT-01` (30-file blast radius â€” backward compatibility required).

**Files.**
```
src/haandvaerker/api/quote_preparations.py
src/haandvaerker/services/wizard_service.py
tests/test_quote_preparations.py
tests/test_wizard.py
```

**Dependencies.** Phase 1 (`wizard_service.build_confirmation_email`
and the send wrapper must exist).

**Acceptance criteria.**
1. `pytest tests/test_quote_preparations.py tests/test_wizard.py`
   passes, including: (a) all 10 existing convert-to-flow tests still
   pass unchanged (backward compat, IMPACT-02); (b) a new test calling
   `convert-to-flow` with no body produces an Enquiry with
   `source == "email"` (default preserved); (c) a test passing
   `{"source": "phone"}` produces `source == "phone"`; (d) a test
   passing `{"send_email": true, "email_subject": "...",
   "email_body": "..."}` with SMTP stubbed to succeed returns
   `email_sent: true` and the four entity IDs are non-null; (e) a test
   with `send_email: true` but SMTP stubbed to raise `SmtpSendError`
   returns 201 with `email_sent: false` and an `email_error` string,
   and the Customer/Enquiry/Project/Quote are still committed
   (queryable afterward).
2. `rg "EnquirySource.email" src/haandvaerker/api/quote_preparations.py`
   shows the hardcoded value now appears only as the **default** of an
   optional parameter, not as an unconditional literal in the Enquiry
   constructor.
3. The convert-to-flow request body is an optional Pydantic model
   (empty body still valid â†’ defaults apply): a test posting an empty
   body returns 201.
4. `ruff check --select E711,E722,F841,F401,B006,B007,S106,RUF100 src/haandvaerker/api/quote_preparations.py`
   reports zero findings; `mypy src/haandvaerker/` passes.

**Deletions.**
- The unconditional `source=EnquirySource.email` literal at
  `quote_preparations.py:248` â€” replaced by the value from the optional
  `source` parameter (default `EnquirySource.email`). This completes
  the CONT-08 residual: after this phase no code path hardcodes the
  channel.

**Subtraction check.** Can the goal be reached by deleting? No â€” the
`source` flexibility and email send are new behaviour. But it is
minimised by *extending the existing endpoint* (E3, the locked
decision) rather than forking a second finaliser: the diff is an
optional parameter and a post-commit `if send_email:` block, not a
parallel code path. Email failure handling reuses the established
invoice-reminder shape (RISK-03) rather than inventing a new one. The
email-send wrapper lives in `wizard_service` (added Phase 1), keeping
SMTP policy out of the route handler (AGENTS.md rule 8).

**Rollback.** Revert this commit. The `source` parameter defaults to
`EnquirySource.email`, so reverting restores byte-identical prior
behaviour; no schema migration; no external state mutated except
emails already sent (one-way notifications, not reversible â€” but a
sent confirmation is benign and idempotent re-runs are blocked by the
`status==converted` guard, RISK-08).

### Phase 4: Wizard frontend

**Goal.** Ship the fullscreen 4-step `/wizard` page wired to the
Phase 1â€“3 endpoints, plus the sidebar entry, never blocking the
operator mid-call.

**Net LoC intent:** ~340 net lines (wizard.html ~300 as a single
self-contained vanilla-JS page, nav.js +1 entry ~3, main.py route ~5,
tests ~30). Justified: this is the only purely-additive phase â€”
wizard.html is a single new static file for the C1 greenfield page,
with no existing wizard page to extend or delete (CODE-07, IMPACT-05);
minimised by avoiding any build step or framework.

**Anchors.** `OPT-C`â†’C1 (new dedicated page), `IMPACT-05` (8 static
pages, no wizard page; new route needed), `CODE-07` (no multi-step UI
exists â€” build fresh), `RISK-04` (QuotePreparation draft = browser-
close recovery), `RISK-06`/`RISK-08` (Step-1 existing-customer search
to reduce duplicates), `RISK-07` (minimum viable = name + task),
`OPT-D`â†’D2 (editable email preview; persistent SMTP notice).

**Files.**
```
src/haandvaerker/static/wizard.html
src/haandvaerker/static/nav.js
src/haandvaerker/main.py
tests/test_wizard.py
```

`main.py` is touched solely to add the `GET /wizard` HTML route
(mirroring the existing per-page routes at `main.py:61-98`).

**Dependencies.** Phases 1, 2, 3 (all wizard endpoints and the
extended convert-to-flow must exist).

**Acceptance criteria.**
1. `pytest tests/test_wizard.py` passes, including a new test asserting
   `GET /wizard` returns 200 with `text/html` and the response body
   contains the step-indicator markup (e.g. a `data-wizard-step`
   attribute or the string `Trin 1`).
2. `rg "wizard.html" src/haandvaerker/main.py` shows exactly one new
   `@app.get("/wizard"...)` route, served before the `/static` mount
   (so the page route takes priority, per the comment at
   `main.py:137-138`).
3. `rg -i "wizard" src/haandvaerker/static/nav.js` shows a sidebar
   entry linking to `/wizard` (e.g. "ðŸ“ž Guided Intake").
4. The four steps are present in `wizard.html` and bind to the correct
   endpoints â€” verify by `rg` for the four call sites in the file:
   `/quote-preparations/` (Step 1 draft create + customer search),
   `/wizard/cvr-lookup` (Step 1), `/wizard/suggestions` (Step 2),
   `PATCH` to `/quote-preparations/` (Steps 2â€“3), and
   `convert-to-flow` (Step 4).
5. Step 4 renders a persistent (not toast) notice when SMTP is
   unconfigured â€” verify the markup contains a non-dismissable notice
   element gated on SMTP status (Iron Law 2), via two machine-verifiable
   checks:
   (a) `rg "sendBtn.*disabled|disabled.*sendBtn|smtp.*disabled|data-smtp" src/haandvaerker/static/wizard.html`
       returns a match (the send button markup carries a conditional
       disable or a `data-smtp` attribute the JS toggles);
   (b) a pytest assertion in `tests/test_wizard.py` confirms the
       `GET /wizard` response body contains a specific
       `data-smtp-status` attribute (or its paired CSS class) that the
       JS reads to show/hide the SMTP notice and disable the
       "BekrÃ¦ft og send" button.

**Deletions.** None. (Frontend is a new page; no existing static page
becomes redundant. Flagged for the user's attention per plan
discipline â€” this is the only purely-additive phase, justified because
C1 is a greenfield page and the cleanup work concentrated in Phases 2
and 3.)

**Subtraction check.** Can the goal be reached by deleting? No â€” there
is no wizard UI to subtract (CODE-07, IMPACT-05). Minimised per ladder
rung 5: a single self-contained `wizard.html` (vanilla JS, matching
the project's no-framework convention) rather than introducing a build
step or framework; `nav.js` gets one entry, not a new navigation
subsystem; wizard step-state lives in JS variables backed by the
server-side QuotePreparation draft (RISK-04) rather than a new
client-state library.

**Rollback.** Revert this commit. Removing the `/wizard` route and the
static file removes the feature entirely; no schema or back-end
contract change in this phase.

## Cross-cutting concerns

- **Company scoping.** Every new endpoint (Phases 1â€“3) takes
  `company_id` exclusively from `CompanyContextDep` (IMPACT-03). The
  Phase 2 `similarity_search` fix brings the one non-compliant search
  path into line (CONT-10). Verified per-phase by `rg` acceptance
  criteria.
- **Graceful degradation / fail-loud (Iron Law 2).** Three new failure
  modes, each handled explicitly and tested: CVR lookup â†’ empty fields
  + `looked_up: false` (Phase 1); AI unavailable â†’ keyword-only +
  `ai_used: false` (Phase 2); email send failure / unconfigured SMTP â†’
  `email_sent: false` + error detail, entities preserved, persistent
  UI notice (Phases 3â€“4, RISK-03). No silent substitution of business
  values.
- **Atomicity & idempotency.** The wizard reuses `convert-to-flow`'s
  single-commit transaction and `status==converted` idempotency guard
  (RISK-01, RISK-08); Phase 3 adds no new partial-state risk because
  the email send happens strictly *after* commit.
- **Tests.** Each phase adds unit/integration tests for its branches
  in `tests/test_wizard.py` (new file, Phase 1). Phase 3 explicitly
  re-runs the 10 existing convert-to-flow tests to prove backward
  compatibility against the 30-file blast radius (IMPACT-01,
  IMPACT-02). Test harness needs no new auth plumbing â€” the existing
  `get_company_context` override applies (IMPACT-06).
- **Lint ratchet & types.** Every phase's acceptance criteria run the
  substance-rule ruff selection from AGENTS.md on net-new files and
  `mypy src/haandvaerker/`.
- **No new dependency.** CVR lookup uses stdlib `urllib.request`
  (OPT-A); no addition to `pyproject.toml`.
- **Sensitive-data masking.** No new endpoint returns full
  `cvr_number`; CVR is request input to the lookup proxy only
  (vision.md Â§6).

## Out of scope

- **Customer dedup constraint.** We add a Step-1 *existing-customer
  search* to help the operator avoid duplicates (RISK-06), but we do
  **not** add a DB `UniqueConstraint` on `(company_id, name)` or
  `(company_id, cvr_number)` and do **not** add lookup-or-create logic
  to `convert-to-flow`. That is a schema change with its own migration
  and blast radius â€” separate plan.
- **Structured historical line items.** Per DP-2, B1 suggestions are
  synthesised heuristically from `HistoricalOffer` flat fields. We do
  not add a structured `line_items` column or migration (debt recorded
  in Architectural posture).
- **HTML / multi-part email.** The confirmation email is plain text
  via the existing `send_email` contract (CONT-09). No HTML email.
- **DAWA address autocomplete (A2).** Only CVR lookup (A1) is in scope;
  free-text address entry remains for the address field.
- **ContactPerson integration.** The wizard uses Customer
  name/phone/email fields only; the unexported `ContactPerson` model
  (CONT-06, IMPACT-04) and a `contact_persons` router are not built.
- **QuoteSequence gap mitigation.** The pre-commit sequence-increment
  gap (RISK-01) is pre-existing behaviour of `convert-to-flow`; we do
  not change it.
- **Extracting a `flow_finaliser` service.** Recorded as future
  pay-down debt; not done now.
- **Refactoring the existing drawer/modal UI** â€” the wizard is a new
  page (C1), the existing `ui.html` drawer is untouched.

## Open questions for the user

None. All five design points are locked in the brief (A1, B1+B2, C1,
D2, E3) and DP-1/DP-2/DP-3 are resolved by those locks.

## Review invocation

After Phase 4 verifies PASS, invoke the `review` skill on
`git diff main...HEAD`. The review skill picks its own reviewer count
and concerns.

