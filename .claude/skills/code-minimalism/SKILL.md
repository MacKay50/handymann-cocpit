---
name: code-minimalism
description: Use before writing, reviewing, planning, or researching any change. Enforced as a gate by the phase-verifier and every reviewer; if not loaded on those runs, the subtraction audit silently did not happen. Load the body — the discipline lives in the ladder and the severity table, not the summary.
license: MIT
compatibility: opencode
metadata:
  audience: implementer, reviewer, researcher, planner, phase-verifier, develop-conductor, review-conductor
  workflow: cross-cutting
---

# Code minimalism — subtract bloat, not quality

> **Loaded this? Read the body.** The description is a trigger,
> not a summary — the discipline is in the ladder, the severity
> table, and the rationalization tables. If you skip the body, the
> gate silently didn't run.

> *The best part is no part. A line removed is better than a line added.*
>
> *But not at the expense of clarity, security, or maintainability.*

Minimalism here is not code-golf and not anti-abstraction.
Minimalism is **anti-bloat**. The distinction:

- **Bloat** = code that complicates the system without earning its
  keep. Speculative abstractions with one caller, dead branches,
  parallel implementations, commented-out blocks, unset feature
  flags, defensive code for impossible states.
- **Quality** = code that pays for itself in security, stability,
  clarity, or near-future maintainability. A well-designed class
  that encapsulates invariants the type system can't express. A
  helper that turns a subtle three-line pattern into a one-line
  call. A file split that makes a subsystem's boundaries obvious.

**When deletion and quality conflict, quality wins.** When
addition and minimalism conflict, minimalism wins. Most of the
time they agree — and when they don't, the question to ask is
"which serves the next person reading this code?"

This skill gives you rubrics for that judgement, biased
(appropriately) toward subtraction because the default gravity of
any codebase is *growth*.

## Extreme no-gos — dead code and masking fallbacks

These are not "bloat" in the ordinary sense. They are **active
hazards** and get treated as **high** or **critical** severity, not
medium. They bypass the normal quality-earns-its-keep balancing
act — they simply have to go.

### 1. Dead code (no identifiable callers)

A function, class, or file with zero callers in the live codebase
is dead. Test-only callers don't count if the test is itself
testing the dead code rather than the live system.

**Severity: high.** Always.

Why: dead code is a maintenance tax with no benefit. Future
readers waste time understanding it; future refactors propagate
through it; future bugs hide in it because nobody runs it.

**Exception:** explicitly-named scaffolding for a feature in
flight (with a tracked plan and a deadline). Calling code is
about to land. Document the scaffolding's lifetime in a comment.

### 2. Masking fallbacks (silent defaults on failed I/O)

Runtime substitution of a plausible-looking value for a failed
external call, missing field, or unexpected exception is a
**high** severity bug by definition. Examples:

```python
# All of these are masking fallbacks. All forbidden.
amount = parsed.get("amount", 0)                      # 0 looks valid; isn't
result = client.fetch() or DEFAULT                     # silently substitutes
try:
    value = external_api()
except Exception:
    value = None                                       # broad except + silent default
```

**Severity: high.** **Critical** when the masked path is in a
high-stakes flow (financial decisions, auth, PII handling, audit
trail).

The distinction the harness draws:

- **Legitimate fallback (allowed):** startup/config fallback to a
  known-good default when the dependency is unavailable at boot.
  Narrow, bounded, logged at WARN, tested, named in code (not a
  generic except).
- **Masking fallback (forbidden):** runtime substitution of a
  plausible-looking value for a failed call, missing field, or
  unexpected exception during normal operation.

Both are called "fallback" in casual speech; only one is safe.

The fix is always the same: **fail loud, escalate, log with
context, increment a counter**. The system caller decides whether
to retry, queue, or surface to a human — never the failing site.

### 3. Same-concept residuals (partial deletion)

When a phase declares it's deleting concept X, but the delete
isn't complete — the function is gone but the helper that
supports it still exists, the doc reference still points at it,
the config key is still in the schema. The phase-verifier's
**Cleanup completeness** gate catches these.

**Severity: high.** **Critical** on high-stakes paths.

The fix: complete the deletion. "Cosmetic follow-up" is not
acceptable — it's how dead code persists across releases.

## The subtraction ladder

Before writing new code, climb this ladder top-down. Stop at the
first rung where the answer is "yes":

1. **Can the requirement be deleted entirely?** Sometimes the
   answer is "we don't actually need this".
2. **Can an existing function absorb this?** A new condition on an
   existing function often beats a new function.
3. **Can a deletion + a small reshape achieve this?** Sometimes
   removing a wrong abstraction *is* the change.
4. **Is the new code earning its keep?** Apply the four-dimension
   architectural fit test:
   - **Separation of concerns** — does this fit the existing
     boundary, or does it cross one?
   - **Pick-up-ability** — can the next engineer find and
     understand it in 10 minutes?
   - **Extensibility** — does this make the next related change
     easier or harder?
   - **Security/stability** — does this widen any trust boundary
     or introduce a new failure mode?
5. **If we can't subtract, can we minimise the addition?** Smaller
   diff > larger diff for the same outcome.

The implementer climbs this ladder before writing any code. The
phase-verifier and reviewer climb it for every diff they see.

## Severity calibration

| Finding type                                       | Severity |
|----------------------------------------------------|----------|
| Dead code (zero callers)                           | high     |
| Masking fallback on high-stakes path               | critical |
| Masking fallback on any other path                 | high     |
| Same-concept residual on high-stakes path          | critical |
| Same-concept residual on any other path            | high     |
| Speculative abstraction (one caller, no obvious second) | medium |
| Parallel implementation of an existing concept     | medium   |
| Commented-out block left in committed code         | low      |
| Unset feature flag still referenced                | low      |
| Magic value where a constant would be clearer      | low      |
| Inconsistent naming across files                   | low      |
| Defensive guard on an impossible state             | low      |
| Pure style nit (single instance)                   | nit      |

## Rationalisations to reject

When you find yourself skipping the subtraction audit, check this
table:

| If you're thinking… | Reality |
|---|---|
| "the code is already there, I'll just add to it" | Adding to wrong code makes it wronger. Climb the ladder. |
| "deletion is risky, addition is safe" | Adding bloat is not safe — it's slow rot. Risk-budgeted deletion is the cheaper option. |
| "I'll clean up later in a follow-up" | Follow-ups for cleanup don't ship. Clean up now or accept the bloat. |
| "the tests cover it, so it's fine" | Tests cover behaviour; bloat is about maintainability. The next engineer pays. |
| "minimalism doesn't apply here, this is genuine quality" | Then the four-dimension test will pass. Run it. |
| "the linter is happy" | Linters catch syntax patterns; bloat is structural. Read the code. |

## Lint ratchet (if your project uses one)

This skill pairs with a project-specific lint ratchet documented
in your `AGENTS.md` (e.g. pylint's `fail-under`, eslint's
`--max-warnings 0`). The phase-verifier enforces the ratchet:

- **No new findings on net-new lines.** Net-new code must be
  lint-clean on substance rules.
- **Substance findings on touched lines must be fixed.** Touching
  a line means bringing it up to standard.
- **No silent config drift.** Lowering `fail-under`, adding to
  `disable`, blanket-disabling rules — all require explicit plan
  authorisation.

The ratchet is asymptotically right: never punitive on day one,
gets stricter as the codebase improves, never loosens.

The single legitimate escape hatch is a line-local disable
comment with a **specific** justification naming the false-positive
mechanism. Vague justifications (`# needed`, `# fine`,
`# by design`) are a high finding — the reader cannot verify the
justification against the actual code.

## When this skill is *not* in scope

- **Genuine new behaviour.** Adding a real feature is addition by
  necessity. Apply the ladder, but accept that step 4 ("does this
  earn its keep?") is the critical question, not "can we
  subtract?".
- **Documentation.** Docs grow with the codebase. Subtraction
  applies (no padding, no boilerplate sections), but addition is
  fine.
- **Tests.** Tests for new behaviour are addition. Tests that
  duplicate existing coverage are bloat.

## What to emit

When this skill surfaces a finding, use the `MIN-` prefix per the
finding schema. Severity per the table above. Always cite
`file:line` or explicit `not_file_based: true`.

Bundled-low style nits should land as **one** `MIN-low` finding
with a list, not N separate findings. The phase-verifier and
reviewer enforce this.
