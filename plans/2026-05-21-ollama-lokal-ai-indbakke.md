# Plan — 2026-05-21-ollama-lokal-ai-indbakke

## Research anchors
- `research/2026-05-21-ollama-lokal-ai-indbakke/researcher-1-all.json` — `chat_completion()` already in `local_ai.py`; insertion point at `message_router.py:127`; Option B (rule-first, LLM enriches at low confidence) selected; risks are 30s timeout on sync endpoint, malformed JSON, and out-of-enum category strings.
- `research/2026-05-21-ollama-lokal-ai-indbakke/brief.md` — Trin 0 is two `.env.example` lines; Trin 1 supplements `primary_category` + `entities` when `confidence < 0.6`; classify call uses 8 s timeout; `MessageCategory` enum validated by code; fallback to rule-based on any failure (WARN already logged in `local_ai.py`).

## Problem statement

The `haandvaerker-demo` inbox classifier in `services/message_router.py` is purely rule-based today. The `local_ai.py` module already exposes a working `chat_completion()` over stdlib `urllib.request`, and the DB enum `ClassificationSource.local_ai` already exists, yet no code path enriches the rule-based result with an LLM call, and `.env.example` does not document `LOCAL_AI_ENDPOINT` / `LOCAL_AI_MODEL`. We add the two env-var lines (Trin 0 simultaneously unlocks Erfaringsbank vector similarity, which is already coded behind `is_enabled()`) and a low-confidence (`< 0.6`) LLM enrichment of `primary_category` + `entities` in `classify_message()` (Trin 1, Option B), gated on `is_enabled()`, with strict JSON + enum validation and silent fallback to the rule-based result on any failure. The `quote_parser.py` / QuotePreparation pipeline is independent and untouched.

## Architectural posture

**Extending the incumbent pattern.** The existing pattern is "rule-based classifier returns a `ClassificationResult` dataclass; `classification_source` is an enum field already accommodating `local_ai`; `local_ai.py` returns `Optional[str]` and logs WARN on failure". The options researcher surfaced Option A (full LLM replacement), Option B (rule-first supplement), Option C (background enrichment via FastAPI `BackgroundTasks`), and Option D (Trin 0 only / do-nothing baseline).

We pick **Option B** because:

- **Separation:** rules remain the deterministic decision spine (Iron Law 3 — "code decides, LLM enriches"); the LLM is bounded to ambiguous cases only (`confidence < 0.6`). Validation logic (enum check, entity-type check, JSON extraction) lives in `message_router.py` next to the data model it guards; HTTP and timeout policy live in `local_ai.py` next to the transport. Policy (when to call LLM) is separated from mechanism (how to call LLM).
- **Pick-up:** the next engineer reads `classify_message()` top-to-bottom and sees: rules run, then `if is_enabled() and result.confidence < 0.6` enrichment runs, with helpers `_extract_json_safe()` and `_validate_llm_enrichment()` adjacent. No new module, no new pipeline, no async machinery.
- **Extensibility:** the threshold (`0.6`) and timeout (`8`) are local constants; if a future plan wants to vary them per-tenant or per-category, the constants become the seam. The validation helper is the seam for future LLM fields (e.g. `is_urgent`).
- **Security/stability:** the LLM call is behind `is_enabled()` (test suite stays green by environment default); fallback is to a fully tested rule-based path; `chat_completion()` already logs WARN on failure (Iron Law 2 satisfied without adding a silent caller-side catch); the 8 s per-call timeout cap (vs the 30 s embeddings default) bounds Uvicorn-thread blocking.

Option A is rejected: it replaces a tested deterministic path with an LLM-dependent one and breaks Iron Law 3's "code decides" posture. Option C is rejected: it requires schema changes (the existing `MessageClassificationUpdate` does not include `classification_source`) and introduces stale-source races for clients polling immediately after classify. Option D alone is rejected by the user's scope (Trin 1 is in scope).

**Debt accrued by extending:** `classify_message()` was previously pure (no I/O). The enrichment branch makes it conditionally I/O-bound. Until tests routinely patch `local_ai.is_enabled`, the no-LLM purity is "by-environment-default" rather than "by-design". The new test fixture in this plan establishes the patching pattern; if Trin 2/3 (Bankafstemning, expense categorisation) follow the same model, factor the `_enrich_with_llm(result)` body into a sibling module (e.g. `services/llm_enrichment.py`) at that time. Tracking marker: a `# NOTE: extracting if Trin 2 reuses this pattern` comment at the enrichment block in `message_router.py`.

## Code-minimalism subtraction check

Is there a version of this work that achieves the goal by deleting code? No. Trin 0 is documentation of two env vars that already drive code that exists (`historical_comparisons.py` calls `generate_embeddings()` behind `is_enabled()` today); the `.env.example` addition is irreducible. Trin 1 introduces an LLM enrichment path the codebase has never had; no existing code substitutes for it. Both helpers (`_extract_json_safe`, `_validate_llm_enrichment`) are net-new functions and necessary because `chat_completion()` returns raw string (RISK-01) and `MessageCategory(...)` raises on out-of-enum values (RISK-05); a future caller in Trin 2/3 reusing them avoids re-implementing the same validation. No file or function is currently dead; nothing identified as deletable.

## Phase 1 — Trin 0 + Trin 1 in one commit-worthy step

Single-phase per Compressed RPIR. The phase leaves the repo working with all 20 existing tests green plus 3 new LLM-path tests, `.env.example` documenting the AI keys, and `classify_message()` enriching low-confidence results when `LOCAL_AI_ENDPOINT` is set.

### What changes

**`.env.example` (Trin 0)** — append a new section after line 31 (`EMAIL_FOLDER=INBOX`):

```
# -- Local AI (Ollama / LM Studio) -------------------------------------------
# Lad LOCAL_AI_ENDPOINT staa tom for at slaa lokal AI fra.
# Naar sat, aktiveres:
#  - Erfaringsbank vektor-similaritet (embeddings paa historiske tilbud)
#  - LLM-berigelse af indbakke-klassifikation ved lav konfidens (<0.6)
#
# Ollama (standard):
#   LOCAL_AI_ENDPOINT=http://localhost:11434
#   LOCAL_AI_MODEL=mistral
#
# LM Studio:
#   LOCAL_AI_ENDPOINT=http://localhost:1234
#   LOCAL_AI_MODEL=mistralai/mistral-7b-instruct-v0.2

LOCAL_AI_ENDPOINT=
LOCAL_AI_MODEL=mistral
```

**`src/haandvaerker/services/local_ai.py`** — add optional `timeout` parameter to `chat_completion()` and propagate it through `_ollama()`, `_lm_studio()`, and `_post()`. Default stays `_TIMEOUT` (30) so existing call sites and embeddings are unchanged. The classify path in `message_router.py` passes `timeout=8`.

- Line 17 (`_TIMEOUT = 30`): unchanged.
- Lines 33-47 (`chat_completion`): add `timeout: Optional[int] = None` parameter; pass through to `_ollama` / `_lm_studio`.
- Lines 50-62 (`_ollama`): add `timeout: Optional[int]` parameter; pass through to `_post`.
- Lines 65-76 (`_lm_studio`): add `timeout: Optional[int]` parameter; pass through to `_post`.
- Lines 79-100 (`_post`): add `timeout: Optional[int] = None` parameter; use `timeout if timeout is not None else _TIMEOUT` in the `urlopen(req, timeout=...)` call at line 84.
- `generate_embeddings` and the two `_*_embed` helpers (lines 103-140): unchanged.

**`src/haandvaerker/services/message_router.py`** — add LLM enrichment and helpers. All additions sit below the existing helpers; do not reorder existing functions.

- Top of file: add `import json`, `import logging` next to existing `import re`; add `from . import local_ai`; add `logger = logging.getLogger(__name__)`.
- Add new module-level constants near the existing `_SPAM_SIGNALS` block:
  - `_LLM_CONFIDENCE_THRESHOLD = 0.6`
  - `_LLM_TIMEOUT_SECONDS = 8`
  - `_LLM_SYSTEM_PROMPT` (Danish-language instruction asking the model to return strict JSON with `category` (one of the 8 `MessageCategory` values), `is_urgent` (bool, advisory only — not assigned), and `entities` (list of `{type, value}` where `type` is one of the 9 `EntityType` values)).
- In `classify_message()` at lines 99-132, between the priority block (line 131) and the `return` (line 132), insert:
  ```
  # NOTE: extracting if Trin 2 reuses this pattern
  if local_ai.is_enabled() and result.confidence < _LLM_CONFIDENCE_THRESHOLD:
      _enrich_with_llm(result, full_text)
  ```
- Add three new helpers at the bottom of the file, each with `from __future__ import annotations` (already present at top) honoured:
  - `def _enrich_with_llm(result: ClassificationResult, full_text: str) -> None:` — calls `local_ai.chat_completion(prompt=full_text, system=_LLM_SYSTEM_PROMPT, max_tokens=512, timeout=_LLM_TIMEOUT_SECONDS)`. On `None` return: log debug and return (rule-based result stands, `chat_completion` already logged WARN per Iron Law 2). On non-`None`: pass to `_extract_json_safe`. If that returns `None`, log debug and return. If non-`None`: pass to `_validate_llm_enrichment`; if validation returns `None`, log debug and return. If validation returns a `(MessageCategory, list[ExtractedEntity])` tuple: assign `result.primary_category = category`, replace `result.entities = entities`, set `result.classification_source = ClassificationSource.local_ai`, re-derive the four boolean flags (`is_quote_related`, `is_project_related`, `is_calendar_related`, `requires_action`) and `priority` using the same logic as lines 115-131. Pull that derivation into a private `_derive_flags_and_priority(result)` helper so both the rule path and the LLM path share one source of truth.
  - `def _extract_json_safe(text: str) -> Optional[dict]:` — strips prose wrapping by locating the first `{` and the last `}` in `text` and slicing between them inclusive; calls `json.loads()` on the slice; on `json.JSONDecodeError` or if no braces found, log WARN with the (truncated to 200 chars) raw text and return `None`. Returns `dict` or `None`. Do not catch generic `Exception`.
  - `def _validate_llm_enrichment(raw: dict) -> Optional[tuple[MessageCategory, list[ExtractedEntity]]]:` — reads `raw.get("category")` and tries `MessageCategory(value)`; on `ValueError` log WARN and return `None`. Reads `raw.get("entities", [])`; for each item, requires `type` and `value` keys; tries `EntityType(item["type"])`; skips items with `ValueError` (logs each as WARN) but keeps valid entities. Returns the tuple. If `category` is missing or not a string, return `None` with WARN.
- Refactor the existing flag/priority block at lines 115-131 into the new `_derive_flags_and_priority(result)` helper and call it from `classify_message()` immediately after `_extract_entities()` (and again from `_enrich_with_llm()` after reassigning `primary_category`). This is a behaviour-preserving extraction that gives the two code paths a single derivation site.

**`tests/test_message_router.py`** — add 3 tests for the LLM path. Place them in a new section header comment block after the existing entity tests.

- New imports at top: `import pytest`, `from unittest.mock import patch`.
- New `monkeypatch`-based test for the happy path:
  - `test_llm_enriches_low_confidence_other_to_quote_request(monkeypatch)`: patches `haandvaerker.services.message_router.local_ai.is_enabled` to return `True` and `haandvaerker.services.message_router.local_ai.chat_completion` to return a stub string `'{"category": "new_quote_request", "is_urgent": false, "entities": [{"type": "person_name", "value": "Jan Hansen"}]}'`. Calls `classify_message(subject=None, body="kort uklar besked")` (which would rule-classify as `other` with `confidence=0.5`, below threshold). Asserts `result.primary_category == MessageCategory.new_quote_request`, `result.classification_source == ClassificationSource.local_ai`, `any(e.entity_type == EntityType.person_name and e.value == "Jan Hansen" for e in result.entities)`, and `result.is_quote_related is True` (flags re-derived from new category), `result.priority == 1`.
- Negative test for malformed JSON:
  - `test_llm_malformed_json_falls_back_to_rule_based(monkeypatch)`: patches `chat_completion` to return `"Sure, here is some prose without any braces."`. Calls `classify_message(body="kort uklar besked")`. Asserts `result.classification_source == ClassificationSource.rule_based` and `result.primary_category == MessageCategory.other` (rule baseline preserved).
- Negative test for out-of-enum category:
  - `test_llm_invalid_category_falls_back_to_rule_based(monkeypatch)`: patches `chat_completion` to return `'{"category": "urgent_unknown_thing", "entities": []}'`. Asserts `result.classification_source == ClassificationSource.rule_based`.
- Pattern for the patches (per RISK-06 / CODE-06: do **not** monkeypatch `os.environ`; patch the function-attribute):
  ```python
  monkeypatch.setattr(
      "haandvaerker.services.message_router.local_ai.is_enabled",
      lambda: True,
  )
  monkeypatch.setattr(
      "haandvaerker.services.message_router.local_ai.chat_completion",
      lambda **kw: '{"category": "new_quote_request", ...}',
  )
  ```

### Explicit deletions

- None of the existing 20 tests are deleted; none of the existing functions are removed.
- The existing inline flag-and-priority block at `message_router.py:115-131` is **moved** (not deleted in net terms) into a new private `_derive_flags_and_priority()` helper. This is a behaviour-preserving extraction so the rule path and the LLM path share one site; the old inline form is removed from `classify_message()`.

This is a near-pure-addition change. The single extraction above is the only structural removal. The user's brief is explicitly additive scope ("add helper", "add tests", "set field"); a multi-phase cleanup is not warranted here. If the planner-verifier flags pure-addition suspicion: the docstring at `message_router.py:4` ("Optional local AI enrichment when LOCAL_AI_ENDPOINT is set") is currently aspirational; this phase makes it accurate — no other dead-code or stale-comment surface is in this file.

### Acceptance criteria

- [ ] AC-1: `python -m pytest tests/test_message_router.py -v` passes all 23 tests (20 existing + 3 new). Run from repo root.
- [ ] AC-2: `python -m pytest tests/ -v` passes the full suite with no regressions (use the same selector the user's CI uses; if absent, `pytest` at repo root).
- [ ] AC-3: `grep -n "LOCAL_AI_ENDPOINT" .env.example` returns a non-empty match, and `grep -n "LOCAL_AI_MODEL" .env.example` returns a non-empty match.
- [ ] AC-4: `grep -n "ClassificationSource.local_ai" src/haandvaerker/services/message_router.py` returns at least one match (the assignment inside `_enrich_with_llm`).
- [ ] AC-5: `python -c "from haandvaerker.services.local_ai import chat_completion; import inspect; assert 'timeout' in inspect.signature(chat_completion).parameters"` exits 0.
- [ ] AC-6: `python -c "from haandvaerker.services.message_router import classify_message; r = classify_message(subject='Forespørgsel om tilbud', body='Vi ønsker tilbud på maling.'); assert r.primary_category.value == 'new_quote_request' and r.classification_source.value == 'rule_based'"` exits 0 (proves the LLM path stays off when `LOCAL_AI_ENDPOINT` is unset and rule-based result is unchanged).
- [ ] AC-7: `grep -nE "except\s+Exception\s*:" src/haandvaerker/services/message_router.py` returns no matches in the new helpers (Iron Law 2 — no broad silent catches; only narrow `json.JSONDecodeError` and `ValueError` are allowed).
- [ ] AC-8: No new third-party imports — `grep -nE "^(import|from)\s+(?!haandvaerker|json|logging|re|typing|dataclasses|__future__)" src/haandvaerker/services/message_router.py` returns no new stdlib-or-third-party imports beyond `json`, `logging`, `re`, `typing`, `dataclasses`. (Sanity: only `from . import local_ai` is the new intra-project import.)
- [ ] AC-9: Manual smoke (documented in commit message, not gated): with `LOCAL_AI_ENDPOINT=http://localhost:11434` set and Ollama running, `POST /message-classifications/classify/{id}` on an ambiguous message returns `classification_source: "local_ai"` within ~8 s; with Ollama stopped, the same request returns `classification_source: "rule_based"` within ~8 s (timeout cap) and `local_ai.py` emits one WARN log line.

### Anchors

CODE-01 (chat_completion exists, no new dep), CODE-03 (insertion point at message_router.py:127), CODE-04 (.env.example missing keys), CODE-05 (30s timeout needs a per-call cap), CONTRACT-01 (no migration — enum exists), CONTRACT-04 (quote_parser independent — untouched), IMPACT-01 (20 tests must stay green), IMPACT-03 (function was pure; now conditional I/O — fixture pattern established), RISK-01 (malformed JSON — `_extract_json_safe`), RISK-02 (timeout cap to 8 s), RISK-03 (Iron Law 2 — caller does not add silent catch; `local_ai.py` already logs WARN), RISK-05 (validate enum before assignment), RISK-06 (patch `local_ai.is_enabled` directly, not `os.environ`), OPT-B (selected over A/C/D).

### Rollback

The phase is a single commit. Rollback is `git revert <sha>` — restores `.env.example`, `local_ai.py`, `message_router.py`, and `tests/test_message_router.py` to pre-phase state. There is no DB migration to undo. There is no new dependency to remove. Operationally, if Ollama causes latency or instability in production after deploy, the immediate non-revert mitigation is to **unset `LOCAL_AI_ENDPOINT`** in the environment and restart — `is_enabled()` returns `False` and the LLM branch is skipped without code changes.

## Out of scope

- `quote_parser.py` and the `QuotePreparation` pipeline (CONTRACT-04) — independent code path; will not be touched even though it parses the same `InboxMessage`. Any LLM enrichment there is a separate plan.
- Async background enrichment (OPT-C) — requires `MessageClassificationUpdate` schema change to accept `classification_source` and introduces stale-source races. Deferred.
- Full LLM replacement of the rule-based path (OPT-A) — rejected on Iron Law 3 grounds.
- Re-classification when `confidence >= 0.6` — the threshold is fixed at `0.6`; making it configurable per tenant / per category is a future concern.
- `is_urgent` field from the LLM response — the prompt asks for it for forward compatibility, but it has no home in the current schema (CONTRACT-02 — no `is_urgent` column) and the validator ignores it. Surfacing it requires a column addition (out of scope).
- Bankafstemning / expense categorisation LLM paths — future Trin 2/3.
- Async / `httpx` migration of `local_ai.py` to replace stdlib `urllib.request` — current sync model is sufficient with the 8 s cap; migration would be a cross-cutting refactor.
- Re-running LLM on re-classify calls — `classify_inbox_message()` at `api/message_classifications.py:66-74` is idempotent (returns cached `MessageClassification` when present and `user_overridden=False`); the LLM runs only on first classification (IMPACT-04). Forcing a re-run is a separate feature.
- Test coverage for `local_ai.py` itself (`chat_completion`, `_post`, embeddings) — out of scope; this phase only exercises the integration point from `message_router.py`.
- Frontend display changes to surface `classification_source: local_ai` distinctly from `rule_based` — the API already returns it (CONTRACT-03); UI work is separate.

## Merge gate

After this phase verifies PASS, invoke the `review` skill on the full diff.
