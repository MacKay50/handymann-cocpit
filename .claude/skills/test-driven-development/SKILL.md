---
name: test-driven-development
description: Use before writing any production code for a feature or bugfix. Skip only for throwaway prototypes, pure config, or generated code (confirm skip with user). Load the body — the Iron Law + rationalization table is the discipline.
license: MIT
compatibility: opencode
metadata:
  audience: implementer
  workflow: implementation
---

# Test-driven development — failing test first

The discipline:

1. **Write the test first.** It expresses the spec.
2. **Watch it fail.** A test you didn't watch fail can't fail.
3. **Write the minimum code to pass.** Not the elegant code; the
   minimum.
4. **Refactor green.** Tests still pass; code gets better.
5. **Repeat.** One small step at a time.

## Iron Law: failing test before production code

> **No production code is written without a failing test that
> requires it.**

Exceptions are vanishingly small. Even when they apply, treat
them as exceptions, not the default.

| Skip is acceptable when... | Why |
|----------------------------|-----|
| Pure config change with no logic | Nothing to assert |
| Pure documentation change | Nothing to assert |
| Generated code (and only the generated parts) | Generator is tested upstream |
| Throwaway prototype | Spec is unstable — confirm with user before skipping |
| Investigative spike that won't ship | Same |

For everything else, write the failing test.

## Rationalisations to reject

| If you're thinking… | Reality |
|---|---|
| "I'll write the test after, same thing" | Test-after means the test is shaped by the code, not the spec. The whole point is the spec drives the code. |
| "this is too simple to TDD" | Trivial code with a wrong assumption embeds wrong behaviour. Write the test first. |
| "I'll TDD next phase" | Next phase has its own test-first cycle. THIS phase needs THIS test first. |
| "the existing tests cover it" | Then your acceptance criterion is "existing tests pass" — but new code needs a new failing-then-passing assertion. |
| "I'm just refactoring" | A refactor that needs no new test means no behaviour changed. Run the existing tests; if they still pass, you're good. If they didn't exist, write characterisation tests first. |
| "the test is obvious from the code" | Then it's obvious to write first. Write it first. |
| "TDD is for greenfield, not legacy" | Legacy is where TDD pays best — the existing tests trap regressions, your new tests trap your new code. |
| "my tests would just mirror the implementation" | Then your test is testing the wrong level. Write a test for the *behaviour*, not the implementation. |

## What "watch it fail" really means

Running the test before writing production code teaches you three
things you can't learn any other way:

1. **The test fails for the right reason.** "Function not found"
   is the right reason on day one. "Wrong return value" is the
   right reason on day two. If the test passes immediately,
   either the test is wrong or the production code already works.
2. **The error message is what your future debugging will see.**
   If the failure message is unhelpful, fix it now while you're
   focused on the spec.
3. **The test is actually wired up.** Surprisingly often, a test
   you wrote isn't picked up by the runner. Watching it fail
   confirms the runner sees it.

## When the test depends on infrastructure that doesn't exist yet

Sometimes the test needs a fixture, a mock, or a test harness
that has to be built. The right order is:

1. Build the harness scaffolding (no tests for the harness itself
   yet — it's about to be exercised).
2. Write the failing test that uses the harness.
3. Watch it fail (now you know the harness works for the negative
   case).
4. Write the production code.
5. Watch it pass.
6. **Then** add tests for the harness itself if it has non-trivial
   behaviour.

This avoids the chicken-and-egg of "I need a test first but the
test needs infrastructure".

## Test quality matters more than test count

A passing test that doesn't actually exercise the new behaviour
is worse than no test — it provides false confidence. The
phase-verifier checks for this in Pass 2:

- **Does the test fail if I delete the production code?** If not,
  the test isn't exercising the production code.
- **Does the test fail if I introduce an obvious bug in the
  production code?** Mutation testing in spirit.
- **Does the test cover the *interesting* branch?** A test that
  hits the happy path of an off-by-one bug doesn't catch the
  bug.

When in doubt, run a manual mutation: change one operator, one
constant, one branch in your production code. If a test still
passes, the test is wrong (or missing).

## Output

The implementer's report should make TDD visible:

- "Wrote failing test at `tests/foo/test_bar.py::test_baz_handles_empty`"
- "Watched fail: `AssertionError: expected escalate, got resolved`"
- "Wrote minimal `Bar.handle_empty()` to make it pass"
- "Refactored: extracted shared empty-check; tests still green"

The phase-verifier checks for this pattern in the diff: are
the tests in the same commit / phase as the code? Were the tests
added before or after the production logic?

## Working with `code-minimalism`

TDD biases toward addition (each cycle adds a test + code). That
can conflict with `code-minimalism`'s subtraction-by-default
posture. The reconciliation:

- **Apply the subtraction ladder before the TDD cycle.** Can the
  feature be deleted? Can an existing function absorb it? If yes,
  TDD doesn't apply (no new behaviour to spec).
- **The test itself can subtract.** A test that says "this branch
  no longer exists" is a deletion test.
- **TDD doesn't override the subtraction audit.** A phase that
  added 200 lines of tests + 200 lines of code without deleting
  anything still triggers the minimalism soft-warn.

Both skills are mandatory loads for the implementer. They
cooperate, not conflict.
