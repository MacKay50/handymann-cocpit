---
name: review-vision-concerns
description: Use when reviewing a slice that touches business logic, the pipeline, policy, admin API, or any architectural surface. Checks `vision.md` + `AGENTS.md` invariants. Mandatory for any review that crosses a vision-defined boundary.
license: MIT
compatibility: opencode
metadata:
  audience: reviewer, phase-verifier
  workflow: review
---

You are reviewing this slice for **vision drift**. Does the change
respect the design principles in `vision.md` and the key design
rules in `AGENTS.md`? Findings get the `VIS-` prefix.

This is one of the most important concerns. Vision drift compounds
silently: each change that bends a principle slightly makes the
next bend slightly more acceptable. Catching them at review is
how the system stays the system.

## Required reading

- `vision.md` in full (it's short — read the whole thing every review)
- `AGENTS.md` §Key design rules
- The slice itself

## How to check each principle

For every numbered principle in `vision.md` §Design principles,
ask:

1. **Did the slice touch the surface this principle governs?** If
   not, skip it.
2. **Does the slice preserve the principle?** Cite file:line for
   how.
3. **If the slice violates the principle, what is the failure mode?**
   The finding's `why_it_matters` should connect to a concrete
   bad outcome.

## Common drift patterns to watch for

| Drift pattern                                          | Why it matters                                 |
|--------------------------------------------------------|------------------------------------------------|
| Binary-outcome principle violated by a partial state   | Downstream caller can't dispatch on the result |
| LLM-recommends-code-decides reversed (LLM directly decides) | Adversarial input now controls a decision  |
| Fail-safe reversed (silent default instead of escalate) | Wrong number ships silently; see code-minimalism §3 |
| Privacy invariant violated (sensitive data reaches surface that shouldn't) | Compliance + trust impact |
| Plane separation crossed (browser talks directly to backend that should be server-side) | Trust boundary widened |
| Flat-structure principle violated by adding a class hierarchy or plugin loader | Future readers can't trace the dispatch path |
| ID-format principle violated (string coerced to int, etc.) | Round-trip data loss; legacy data breaks |
| Audit-row principle violated (mutation without audit trail) | Operations can't reconstruct what happened |

## The "rule 9" check (if your AGENTS.md has it)

If your `AGENTS.md` includes a "design for easy pick-up and change"
rule, every review should also check:

- **Separation of concerns** — did the change blur a boundary?
- **Pick-up-ability** — can a new engineer find the change in 10
  minutes?
- **Extensibility** — did the change make the next related change
  easier or harder?
- **Security/stability posture** — did the change widen a trust
  boundary or introduce a failure mode?

These map to `VIS-` findings with severity calibrated against the
principle's stakes.

## Severity calibration

| Finding | Severity |
|---|---|
| Vision invariant violated on a critical-path surface (financial, auth, PII) | critical |
| Vision invariant violated on any other surface | high |
| Drift toward violation (still preserves invariant but bends it) | medium |
| Inconsistency in how a principle is applied across files | low |
| Documentation drift (docs say X, code does Y) | low |

## What `cleared[]` to populate

- "Verified binary outcomes at file:line — handler returns
  resolved | escalated, no partial states."
- "Verified fail-safe at file:line — exception path escalates
  rather than substituting a default."
- "Verified plane separation at file:line — no direct external
  fetch from browser context."

## Anti-examples

- "Could violate principle X" without citation — drop or raise as
  open question.
- "The general design feels off" — vague, not a finding. Either
  cite a specific principle violation or drop.
- "The principle isn't really important here" — that's the
  drift, not the absence of a finding. The principle is a
  principle; bending it is the finding.
