# Auto-commit policy (develop-conductor)

The conductor **commits clean phases automatically** — phase
boundaries on git history, useful `git bisect`, no "should I
commit?" prompt after every phase.

## Iron Law

> **Commit only on Section-3 PASS (clean).** Never on `PASS WITH
> FOLLOWUP`. Never on `FAIL`. Never when secrets check is flagged.
> Never when the diff is outside the phase's declared scope.

Section 1's `**Acceptance:** PASS` is a per-pass readout, not the
gating verdict — acceptance can be PASS while the Section 3 phase
verdict is FAIL (e.g. a critical finding blocks). Only Section 3
gates auto-commit.

## When to auto-commit

Commit automatically when the phase-verifier returns Section 3
PASS (clean):

- Every acceptance criterion met with evidence.
- Zero critical / high findings.
- Zero unresolved medium findings.
- No `ambiguity_questions` outstanding (structured field the
  phase-verifier emits in Section 2 JSON — parse it, don't read
  Section 3 markdown).
- No `subtraction_warning` unresolved (user already acknowledged
  or plan authorised pure-addition).
- **Lint gate held** (when phase touched language-relevant files).
  Net-new code lint-clean, substance findings on touched lines
  fixed, lint config unchanged (or plan-authorised).
- **Frontend lint clean** (when phase touched UI files).

## Do NOT auto-commit when

- `PASS WITH FOLLOWUP` — ask the user first (they may fix in-place
  or split).
- `FAIL` — never.
- The phase modified the plan document itself (plan edits need
  user sign-off).
- The diff includes files outside the phase's declared scope —
  surface drift to the user before committing.
- A secret-shaped file appears in the diff. The phase-verifier's
  Section 1 `**Secrets check:**` field is the authoritative
  signal; if `flagged`, halt regardless of verdict. Belt-and-
  braces, run

  ```bash
  git diff --name-only --cached \
    | rg -i '\.env(\.|$)|credentials|secret|\.pem$|\.key$|id_rsa|id_ed25519'
  ```

  yourself before committing.

## Commit procedure

1. `git status` — confirm the diff matches what the phase-verifier
   reviewed. Nothing extra, nothing missing.
2. `git add <files-the-phase-declared>` — only files the plan's
   phase called out, plus tests for those files. Never
   `git add -A` / `git add .` (catches unintended drift).
3. `git diff --cached --stat` — verify staged changes match intent
   AND capture Net LoC for the commit message body (authoritative;
   not the implementer's report).
4. `git commit -m "<subject>" -m "<body>"` with the template below.
5. `git log -1 --stat` — confirm the commit landed as expected.
6. Report the commit SHA to the user along with the phase summary.

## Commit message template

This template assumes **conventional commits** (`feat(scope):`,
`fix(scope):`, `refactor(scope):`, `chore(scope):`, `docs(scope):`).
Run `git log --oneline -20` to confirm current convention before
committing — adapt the template to match what the repo already
uses.

```
<type>(<scope>): <one-line summary, imperative mood, lowercase>

Phase <N> of plan: <plan-title>

<optional: 1-3 sentences on intent / failure mode resolved.>

Net LoC: <+A / -B (net ±C) across D files>
Deletions:
- <bullet from implementer's Deletions section, or "none">

Findings (resolved): <count or "none">
Follow-ups: <count or "none">
```

**Scope choice:** narrowest accurate scope from the diff. Match
your project's typical scopes (look at `git log` to see what's
been used). Multiple scopes → pick primary; mention others in
the body.

**Type choice:**
- `feat` — new capability the user can observe.
- `fix` — bugfix for documented behaviour.
- `refactor` — code movement, no behaviour change.
- `chore` — build / deps / tooling / housekeeping.
- `docs` — documentation only.
- `test` — tests only (rare — usually part of a `feat` or `fix`).

Example:

```
feat(api): add per-customer rate limit

Phase 2 of plan: tighten-api-rate-limits

Prevents a single customer from making more than N requests per
UTC minute by reading the rolling count from Redis and rejecting
past the cap.

Net LoC: +48 / -12 (net +36) across 3 files
Deletions:
- removed obsolete `legacy_max` knob from config.py
- removed commented-out block in api/middleware.py:42-58

Findings (resolved): none
Follow-ups: 1 (track deprecation of MAX_PER_MIN env var)
```

## Commit hygiene rules

- **Subject ≤ 72 chars.** Imperative mood. No trailing period.
- **Lowercase subject after the type/scope prefix** (matches the
  conventional-commits norm, but defer to `git log --oneline -20`
  if your repo's style differs).
- **Body wraps at 72.** Factual, not promotional.
- **Never include "AI-generated" / "Claude" / "Copilot" /
  "Co-authored-by" signatures** unless the user has explicitly
  asked. The user is the author; you are a tool.
- **Never force-push, never `git reset --hard`, never amend a
  commit that has been pushed.** Amend is allowed only for the
  previous conductor-made commit AND only if the user explicitly
  asked to amend.
- **Hook failures are not reasons to amend.** If a pre-commit
  hook modifies files and the commit succeeds, amend to include
  the auto-fix. If the hook rejects the commit, fix and create a
  NEW commit.

## What to do when auto-commit is declined

If the user pauses the flow after PASS and before the conductor
commits (they want to look at the diff first), honour that. Don't
commit after the next message unless the user re-approves.

## Interaction with stage 4

After the final phase commits cleanly, stage 4 runs on
`git diff <base>...HEAD` — base is the branch point. Per-phase
commits make it easy for the user to see review findings as "this
finding relates to commit X" and to bisect if needed.
