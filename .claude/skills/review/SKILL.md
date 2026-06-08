---
name: review
description: Use when the user says "review", "audit", "sanity check", "pre-prod check", "security review", "production readiness", or when finishing a phase / preparing a PR / cutting a release. Also use proactively when a change touches a high-stakes path or multiple subsystems. Primary quality gate; prefer over ad-hoc review. Works autonomously — figures out what to review from git state when no context is given.
license: MIT
compatibility: opencode
metadata:
  audience: review-conductor
  workflow: review
---

# Review — multi-concern code/system audit

This skill is the playbook the `review-conductor` runs. Scope
resolution, partition assignment, reviewer fan-out, synthesis,
verdict.

## Three modes

The conductor picks one based on what the user asked for:

| Mode          | Trigger                                 | What gets reviewed                       |
|---------------|-----------------------------------------|------------------------------------------|
| **Slice**     | "review phase 3", "review this PR"      | One git diff range over a focused slice |
| **Partition** | "pre-prod check", "review the whole change" | Whole diff partitioned across reviewers by subsystem |
| **State**     | "is the codebase ready to ship?"        | Live HEAD, no diff — release-readiness  |

Slice mode is the default. Partition mode kicks in when the diff
crosses subsystems. State mode is rare — used pre-release.

## Step 1: Scope resolution

When the user provides scope, use it. When they don't:

- "review the recent work" → `git diff $(git merge-base HEAD main)..HEAD`
- "pre-PR" → same as above, on the current branch
- "audit the auth code" → `src/auth/**` regardless of diff state
- No context → ask the user. Don't guess what they meant.

Output the resolved scope as a one-liner before fanning out:

```
Scope: src/api/middleware.py + tests/api/test_middleware.py
       (diff range: main..HEAD, 3 files, +127 / -14)
```

## Step 2: Partition the slice (if needed)

For partition mode, split the diff by subsystem:

| Partition           | Reviewer concerns                                |
|---------------------|--------------------------------------------------|
| Core business logic | vision, reliability, data, security              |
| API / pipeline      | security, vision, reliability                    |
| Auth / admin        | security, vision, operations                     |
| External integration | data, security, reliability                    |
| UI                  | ux, security, vision                             |
| Schema / migration  | data, operations, reliability                    |

Each partition gets its own reviewer with its own concern list.
The conductor assigns; reviewers don't pick.

## Step 3: Reviewer scaling

| Slice size | Reviewers |
|---|---|
| Single file or single subsystem | **1** |
| Two subsystems or significant cross-cutting | **2** |
| Whole-change review across 3+ subsystems | **3-4** |
| Pre-release state-of-codebase | **3-4** |

Hard cap: 4. Coverage comes from concerns loaded per reviewer, not
from spawning more reviewers.

## Step 4: Concern assignment

Every reviewer always loads:

- `code-minimalism` (mandatory subtraction audit on every review;
  `MIN-` finding prefix)

Plus the concerns the conductor assigned for that partition. The
reviewer's `concerns[]` output array MUST include `minimalism` and
the assigned ones — this is the contract that lets the conductor
verify the audit happened.

## Step 5: Fan out (parallel)

Spawn N `reviewer` subagents in the same turn. Each gets:

- The resolved scope (paths + diff range).
- Its concerns to load.
- Any domain skills (per `AGENTS.md`).

Reviewer prompt template lives in `references/reviewer-prompts.md`
(if you need one — most projects can pass a 5-line prompt).

## Step 6: Synthesise (conductor does this — no judge subagent)

1. **Read each reviewer's JSON.** Validate against
   `references/finding-schema.md`.
2. **Deduplicate** findings across reviewers; merge same-spot
   findings into one (concordance is signal).
3. **Normalise severity.** When two reviewers disagree on severity
   for the same finding, take the higher.
4. **Surface ambiguity.** Any `ambiguity_questions[]` from any
   reviewer goes to the user — frame the choice, never silently
   pick.
5. **Cluster**. Three small `MIN-low` findings from three
   different reviewers that all point at the same refactor
   opportunity become one `MIN-medium` with a clear scope.
6. Write the final markdown report.

## Step 7: Verdict

Per `references/finding-schema.md`. Apply the rules:

- **SHIP** — no critical, no high, mediums tracked or absent.
- **SHIP WITH FOLLOWUP** — no critical, no high, mediums require
  user acknowledgement.
- **DO NOT SHIP** — any critical or high.
- **BLOCKED** — `scope_blocker` populated; can't review.

## Hard rules

- **Read-only.** No edits anywhere. The conductor's permission
  enforces this; reviewers also have `edit: deny`.
- **Cite or it's noise.** Every finding has `file:line` or
  `not_file_based: true` with justification.
- **Apply every loaded concern.** Don't skip. Concordance is
  signal.
- **Faithful synthesis.** If reviewers say `DO NOT SHIP`, the
  report doesn't say "probably fine".
- **Ask on ambiguity.** Same Iron Law as `develop-conductor`. The
  conductor surfaces every `ambiguity_questions[]` to the user.

## When NOT to use this skill

- The user wants you to **fix** something — Tab to `develop-conductor`.
- The user wants to **explore** the codebase — use the built-in
  `explore` agent.
- The user wants a **plan** — Tab to `develop-conductor`.
- The user wants **architectural-shape advice** ("is this ready to
  build on?") — that's a refactor-audit, not a review. Different
  output shape; this skill is for finding problems, not proposing
  reshapes.
