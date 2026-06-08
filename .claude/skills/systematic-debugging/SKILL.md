---
name: systematic-debugging
description: Use on any bug, test failure, integration outage symptom, edge case behaviour, or unexpected behaviour — before proposing a fix. Especially when 1-2 patches already failed, or under time pressure. Load the body — the Iron Law + rationalization table is how this skill works.
license: MIT
compatibility: opencode
metadata:
  audience: implementer, phase-verifier, reviewer
  workflow: bug-fix
---

# Systematic debugging — root cause before patch

The discipline: before patching, **reproduce the bug deterministically
and explain the root cause**. Patches without root cause are wishes,
not fixes.

## Iron Law

> **Patch only after the root cause is named with evidence.**

The patch is the easy part. The hard part is the four steps before
the patch:

1. **Reproduce.** Make the bug fail on demand. If you can't
   reproduce, you don't have a bug — you have a symptom report.
2. **Localise.** Narrow the failure to one component, one function,
   one line. Bisection is the tool — git, code paths, inputs.
3. **Explain.** Name the root cause with `file:line` evidence.
   "Why does this fail?" answered concretely, not "I think...".
4. **Predict.** Propose the fix and predict what changes. Run the
   reproduction; check the prediction.

Only then patch.

## Rationalisations to reject

Bugs lure you into shortcuts. Reject them:

| If you're thinking… | Reality |
|---|---|
| "I think it's the X function, let me just patch it" | You think it's X; you don't *know* it's X. Reproduce, localise, then patch. |
| "the symptom went away after my change, must be fixed" | Symptom-going-away ≠ root-cause-fixed. The bug may now manifest somewhere else. Reproduce against the original repro. |
| "production is on fire, no time to debug" | Wrong patches under fire create more fires. Take 5 minutes to reproduce; saves 50 minutes of compounding patches. |
| "the stack trace is obvious" | Stack traces show *where* an error surfaced, not *why*. Localise to the function that violated its contract, not the function that raised. |
| "users say it's intermittent, can't reproduce" | Intermittent means you haven't found the trigger. Find the trigger. Race condition? Timing? Specific data shape? |
| "I've patched this kind of bug before" | Pattern-matching is fast but unreliable. The fix that worked last time may be the wrong fix this time. Verify. |
| "the unit test passes, must be working" | Unit tests pass against your assumptions. The bug lives in your assumptions. |
| "the bug is in third-party code, can't fix" | Then the bug in your code is "we used the third-party code wrong". Find that bug. |

## The four steps in detail

### 1. Reproduce

If you can't run a command and watch the bug, you don't have a
bug, you have an anecdote. Reproduce by:

- Replaying the user's reported flow.
- Crafting a minimal failing test.
- Replaying production logs against a local instance.
- Diff'ing against the last known-good state.

The output of step 1 is **a command that fails reliably**. Write
it down — you'll run it again in step 4.

### 2. Localise

Bisect. Use whatever bisection lever the situation gives you:

- **`git bisect`** for "it worked yesterday".
- **Input bisection** for "it works for case A, not case B" —
  shrink the input until the failure flips.
- **Code-path bisection** — add a print/log at the suspected
  function entry; does it fire? Move the marker.
- **Time bisection** — does it fail before or after this
  database call? Before or after this LLM call?

Stop when you have a single function or line. If you can't
narrow further, you don't yet understand the system well enough —
go back to step 1 and gather more reproductions until the pattern
emerges.

### 3. Explain

Name the root cause. The acceptable forms are:

- "Function X at file:line returns Y when it should return Z
  because <specific code-level reason>."
- "Module A's contract says X but module B is calling it as if it
  said Y — file:line for both."
- "The state machine's invariant `<specific>` is violated when
  `<specific input>` arrives because `<specific code path>`."

Unacceptable forms:

- "Probably an off-by-one somewhere."
- "Race condition, hard to say where."
- "I think it's a config issue."

If you can only explain in unacceptable forms, you haven't
finished step 2. Bisect more.

### 4. Predict and verify

Before applying the fix, predict:

- "After the fix, the reproduction command will <specific output>."
- "Tests A and B will still pass. Test C will start passing."
- "No other behaviour changes — the fix is local."

Then apply the fix and run the reproduction. Did the prediction
hold? If not, the root cause is wrong, not the fix. Go back.

## When you're stuck

After 30 minutes on step 2 with no localisation, **stop and
escalate**. Tell the user what you tried, what you saw, what you
think it might be, and ask. Two reasons:

1. The user often has context (recent prod changes, known issues
   in adjacent systems) that you don't.
2. Continuing to grind without progress is how shallow patches
   ship.

Specifically *don't*:

- Apply a patch you can't justify, hoping it works.
- Add defensive code that masks the symptom without fixing the
  root cause.
- Mark the bug "intermittent" and move on.

## Bug-fix phases in the harness

When the implementer is in a bug-fix phase, it loads:

- `code-minimalism` (always)
- `test-driven-development` (always)
- `systematic-debugging` (this skill)

The TDD cycle for a bug fix is:

1. Reproduce the bug (this skill, step 1).
2. Localise (step 2).
3. Explain root cause (step 3).
4. **Write a failing test that captures the root cause.** Not the
   symptom — the root cause. The test should be the reproduction,
   distilled.
5. Watch it fail.
6. Apply the minimum fix that addresses the root cause.
7. Watch the test pass.
8. Run adjacent tests to verify no regression.
9. Predict & verify (step 4 of this skill).

The phase-verifier checks: does the new test capture the root
cause, or just the symptom? A test that asserts "function returns
non-None" when the bug was "function returned 0 instead of None"
captures the symptom badly — a deeper version of the bug would
slip through.

## Common bug patterns and where they hide

This is not a complete list, but a starter for triage:

- **Off-by-one** → boundary tests; especially first/last/empty.
- **Null/missing field** → masking fallback (`code-minimalism`
  §2); usually `.get(..., default)` or `or DEFAULT`.
- **Race condition** → time-based bisection; `time.sleep` in tests
  is a smell; locks/atomics need careful audit.
- **Stale state** → cache TTLs, memoization, module-level state.
- **Wrong contract** → caller and callee both look fine in
  isolation; the bug is at the boundary.
- **Encoding** → UTF-8 vs Latin-1; serialised vs deserialised; one
  side trims, the other pads.
- **Timezone** → naive datetime + UTC datetime; DST transitions;
  log timestamps that don't match.
- **Quantification** → "every customer" vs "every customer with X";
  the missing predicate.

## Output

The implementer's report should show the four steps:

- "Reproduced: `<TEST_RUNNER> tests/foo/test_bar.py::test_specific` failed."
- "Localised: bug is in `src/foo/bar.py:142` — `compute_total` returns
  `0` for empty `items` list because `sum(items)` is `0` and the
  caller doesn't distinguish 'empty' from 'all zero'."
- "Root cause: caller's contract assumed `compute_total` returned
  `None` for empty input; implementation returned `0`."
- "Fix: caller now branches on `len(items) == 0` before calling.
  Reproduction now passes; adjacent tests still green."

This pattern shows up clearly in commit messages and is what the
phase-verifier checks for in bug-fix phases.
