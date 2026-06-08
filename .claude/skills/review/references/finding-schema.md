# Finding schema

Every `reviewer` subagent MUST emit a single JSON object in this
shape. The conductor merges these mechanically — deviations break
the pipeline. If a field doesn't apply, emit it with an empty array
or null, not by omission.

The reviewer is *generic* and applies multiple concerns at once.
The top-level field is `concerns` (array) and every finding tags
which concern(s) surfaced it.

## Schema

```json
{
  "concerns": ["security", "vision", "operations"],
  "scope": {
    "paths": ["src/api/middleware.py"],
    "diff_range": "main..HEAD",
    "change_type": "new-feature"
  },
  "summary": "One-paragraph TL;DR of what this reviewer saw across all loaded concerns.",
  "findings": [
    {
      "id": "SEC-01",
      "concern": ["security", "reliability"],
      "title": "Rate-limit threshold taken from request body without bounds check",
      "severity": "critical",
      "confidence": "high",
      "where": {
        "file": "src/api/middleware.py",
        "line": 214,
        "symbol": "evaluate_rate_limit"
      },
      "evidence": "The `threshold` field on the request body flows directly into `enforce_limit` without validation. Snippet:\n\n    threshold = body.get(\"threshold\", 0)\n    decision = enforce_limit(threshold, ...)\n\n(file:line shown above.)",
      "why_it_matters": "An external request can request an arbitrarily large threshold. The limit engine has a max-per-window cap but only applies it after threshold normalisation, which rounds in the attacker's favour.",
      "suggested_fix": "Clamp `threshold` to the configured maximum before passing to `enforce_limit`. Add a test at tests/api/test_middleware.py that sends threshold > max and asserts rejection.",
      "tags": ["input-validation", "trust-boundary"]
    }
  ],
  "cleared": [
    {
      "title": "Auth check ordering",
      "detail": "Verified middleware.py:83 runs auth before any business logic. Matches vision.md §3.7."
    }
  ],
  "scope_blockers": [],
  "ambiguity_questions": [
    {
      "id": "Q-01",
      "finding_refs": ["MIN-02", "VIS-04"],
      "question": "minimalism says delete the forwarding wrapper; vision says the separation is intentional for downstream isolation. Which resolution?",
      "options": [
        "Delete the wrapper and inline its one call site.",
        "Keep the wrapper and document intent at the call site.",
        "Keep both findings as tracked follow-ups for a separate refactor."
      ]
    }
  ],
  "reviewer_notes": [
    "Did not look at admin API; out of scope per task prompt."
  ]
}
```

## Field rules

- `concerns`: array of the concern names this reviewer applied
  (e.g. `["security", "vision", "operations", "baseline",
  "minimalism"]`). Names match the concern-skill names with
  `review-` and `-concerns` stripped. **`minimalism` is included
  on every review** because the subtraction audit from
  `code-minimalism` is a mandatory pass.
- `scope`: echo the scope you were given. Helps the conductor
  confirm you stayed on-task.
- `summary`: 1-3 sentences, plain prose, what this reviewer saw
  across all loaded concerns.
- `findings[]`: zero or more. Each finding:
  - `id`: `<CONCERN3>-<NN>`, e.g. `SEC-01`, `REL-02`, `VIS-01`,
    `DAT-03`, `OPS-04`, `MIN-05`. Unique within this review run.
  - `concern`: array of concerns that surfaced this finding. Often
    one; multi-concern findings list all (concordance is signal).
  - `title`: imperative, specific. "X is wrong because Y." Not
    "Problems in auth module".
  - `severity`: `critical` / `high` / `medium` / `low` / `nit`.
    See severity rubric below.
  - `confidence`: `high` / `medium` / `low`. Low confidence is
    fine and useful — the judge weights by it.
  - `where`: file + line + symbol (function/class). If not
    file-based, set `"not_file_based": true` and explain in
    `evidence`.
  - `evidence`: concrete. Paste the smoking-gun snippet. Cite docs
    if the finding is a spec mismatch (e.g. vision.md §X).
  - `why_it_matters`: connect it to a real failure mode — a user,
    an attacker, an operator, a production incident shape. If you
    can't describe a failure mode, the finding is probably noise.
  - `suggested_fix`: actionable. Don't need to be perfect; need to
    be a starting point the author could run with.
  - `tags[]`: free-form keywords, useful for the judge's clustering.
- `cleared[]`: things you checked and didn't find a problem with.
  This is *critical* — it's how the conductor knows the surface
  was covered rather than skipped. Be specific: "checked X at
  file:line, verified invariant Y holds".
- `scope_blockers[]`: anything that stopped you from reviewing. If
  populated, the conductor will halt and report to the user.
- `ambiguity_questions[]`: zero or more structured questions for
  the conductor to resolve with the user. Each item has `id`,
  `finding_refs` (array of finding IDs), `question`, and `options`
  (2-4 concrete resolutions). The conductor treats a non-empty
  `ambiguity_questions[]` as a blocker — the user must resolve
  before the change ships. Keep these to *real* ambiguity:
  severity disputes, concern conflicts (security vs ops), drift
  the author should confirm.
- `reviewer_notes[]`: anything else the judge should know — what
  you deliberately skipped, what assumption you made, what you'd
  want to look at next.

## Severity rubric

- `critical` — will break production or leak data. Block merge.
  Examples: secret in committed file; PII sent to LLM; refund
  amount unbounded; admin endpoint without auth check.
- `high` — will cause incidents, silent data wrong-ness, or
  security regressions. Block merge unless there's a tracked
  follow-up. Examples: missing timeout on external call;
  off-by-one in policy; missing audit row on a mutation.
- `medium` — will bite us in a few weeks. Follow-up ticket.
  Examples: no test for new branch; log line missing correlation
  ID; missing loading state on a new page.
- `low` — would be nice to fix. Examples: duplicated helper;
  magic number; inconsistent naming; commented-out block; unused
  argument; defensive guard on an impossible state; comment that
  should be a rename (`MIN-` findings typically land here or
  medium).
- `nit` — taste. Mention once.

## Confidence rubric

- `high` — you read the code, you have a citation, the failure
  mode is concrete.
- `medium` — you read the code, the failure mode is plausible but
  you couldn't reproduce or didn't trace every branch.
- `low` — pattern-matching, not confirmed. Judge may ask for a
  deeper look.

## Anti-examples (don't emit these)

- `"title": "Consider adding more tests"` — no location, no
  specific gap, no failure mode. Not a finding.
- `"evidence": "This function looks complex"` — not evidence.
  Cite the actual problem.
- A finding without `where` and without `not_file_based: true`.
  Reject your own output if you produce this.
