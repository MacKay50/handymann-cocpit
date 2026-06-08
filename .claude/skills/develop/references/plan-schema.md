# Plan schema

Plans are markdown, not JSON — humans read them. But they follow a
strict template so the verifier and the implementer can consume
them mechanically.

## Template

```markdown
# Plan: <short descriptive title>

**Path:** plans/<YYYY-MM-DD>-<slug>.md
**Created:** <YYYY-MM-DD>
**Research:** research/<YYYY-MM-DD>-<slug>/
**Status:** draft | approved | in-progress | complete

## Research anchors

<List every artifact under `research/<slug>/` with a one-line
summary so a reader can jump straight to the evidence. These are
gitignored — regenerate with `develop-conductor` if missing.>

- `research/<slug>/brief.md` — synthesised brief the user approved.
- `research/<slug>/researcher-1-code+contract.json` — call sites
  of <feature>; schema field availability; config shape.
- `research/<slug>/researcher-2-risk.json` — rollout risks; legacy
  data interaction; operator error modes.
- `research/<slug>/researcher-3-options.json` — three approaches
  with tradeoffs.

Phases below cite specific finding IDs (`CODE-03`, `RISK-01`,
`OPT-B`) where a decision is anchored in research evidence.

## Problem
<One paragraph. What are we solving and why now? Echo the approved
problem statement. If the research brief revealed a more precise
framing, use it.>

## Approach
<One paragraph. At a high level, what are we doing? Not the
phase-by-phase — the shape of the change. Which option from the
options concern (cite `OPT-A` / `OPT-B` / ...). Which cross-cutting
decisions are baked in.>

## Architectural posture

<One paragraph. What incumbent pattern does this change touch, and
are we *extending* it or *redesigning* it? Answer the four
architect questions from `AGENTS.md` rule 9:

- **Separation of concerns** after this plan: what belongs where,
  and does any change blur a boundary?
- **Pick-up-ability**: can a new engineer find and understand the
  new shape in under 10 minutes? What naming / layout decisions
  support that?
- **Extensibility**: what is the next related change, and is it
  easier after this plan than before?
- **Security / stability posture**: does this plan widen any trust
  boundary, add a failure mode, or make an invariant harder to
  verify? If yes, name the mitigation.

If extending an incumbent pattern, cite the options-researcher's
redesign option (`OPT-?`) and justify why extension wins on net.
Name the debt the extension accrues and when it will be paid down.
Silent extension of a `strained`-fit pattern is a plan-verifier
reject.

If redesigning, name what the new shape is, what it replaces, and
which phases do the replacement work. The redesign must leave the
system better shaped, not differently shaped — subtraction over
rearrangement.

Trivial plans that touch no existing pattern may say:
"No incumbent pattern touched — greenfield addition." Plan-verifier
accepts this only when the research brief confirms the slice is
truly greenfield.>

## Invariants preserved
<Bullet list. Which vision/AGENTS invariants does this plan
explicitly preserve? Not "all of them" — list the ones the plan
actively respects so the verifier can check.>

## Phases

### Phase 1: <name>

**Goal.** One sentence.

**Anchors.** `CODE-03` (rate_limit.check call sites),
`CONT-05` (config shape). Cites specific findings from the
research artifacts listed above.

**Files.**
```
src/api/middleware.py
tests/api/test_middleware.py
```

These are the ONLY paths the implementer may touch in this phase.
The phase-verifier reads this block to filter every gate to just
these paths. Touching a file not listed here is a
stop-and-propose-deviation event, not a "while I'm here" edit.

**Dependencies.** None.

**Acceptance criteria.**
1. `<TEST_RUNNER> tests/api/test_middleware.py` passes, including
   new tests covering X and Y.
2. `rg "old_helper\(" src/` returns zero hits — old helper fully
   replaced.
3. `src/api/middleware.py` exports `new_helper` with type signature
   `(ctx: Context) -> bool`.

**Deletions.**
- `src/api/middleware.py:old_helper` (replaced by `new_helper`).
- `src/api/middleware.py:_legacy_normalise` (now unreachable).
- commented-out block at `src/api/middleware.py:42-58`.

**Subtraction check.** Can this phase be achieved purely by
deleting? No — `new_helper` has distinct behaviour. But the net
change is still negative (see deletions above).

**Rollback.** Revert this commit; no schema changes.

### Phase 2: <name>
...

## Cross-cutting concerns

<Bullet list of things that apply across phases. For each, say how
it's handled.>

- **Audit rows.** Every mutation in phases 2 and 3 writes an audit
  row with the verified user identity.
- **Metrics.** Phase 2 adds `<counter_name>` with labels `<list>`.
- **Docs.** Phase 3 updates `docs/<file>.md` §Section.
- **Tests.** Each phase adds unit tests for its new branches. An
  integration test in phase 4 covers the full flow.

## Out of scope

<Bullet list. What this plan does NOT do. Helps the implementer
resist scope creep and helps the reviewer know what to ignore.>

- We are not adding per-customer overrides (decision deferred —
  not in the research brief).
- We are not refactoring the existing middleware structure
  (separate plan).
- We are not changing the dashboard layout (only adding the new
  field to existing forms).

## Open questions for the user

<Numbered list. Only include if there ARE open questions — empty
list means "plan is complete as-is". The user answers these before
approving.>

1. Should the default `max_per_minute` be 100 or 50? Research
   found both mentioned in different places.
2. Should the new field be editable by operators, or admin-only?

## Review invocation

<After all phases verify PASS, the plan ends with invoking the
`review` skill on the full diff. Usually just:>

"After phase N verifies, invoke the `review` skill on
`git diff main...HEAD`. The review skill picks its own reviewer
count and concerns."
```

## Rules

- **Phases are commit-worthy.** A phase should leave the repo in
  a working state — tests pass, build passes. Not "phase 3 fixes
  phase 2's broken state".
- **Acceptance criteria are runnable.** Each criterion is a
  command (test runner, curl, rg, build) or a file-state check.
  "Works correctly" is not a criterion.
- **One phase, one concern.** A phase that adds a model, a
  migration, an endpoint, and a UI is four phases.
- **Rollback per phase.** Even if trivial ("git revert"), state
  it. Forces the planner to think about irreversible changes
  (migrations, external API calls, etc.).
- **Out-of-scope is mandatory.** Empty "out of scope" section is
  a red flag — it means the planner didn't think about what they
  were explicitly not doing.
- **Every phase has a Deletions section and a Subtraction check.**
  Empty deletions is allowed but is itself a signal — a plan
  where no phase deletes anything means the system is growing
  purely additively, which rarely holds up over time. At least
  one phase in any multi-phase plan should be a cleanup / removal
  phase.
- **Net LoC sanity.** For each phase estimate net LoC intent.
  Phases with net addition > 100 lines should be flagged and
  justified; the phase-verifier's minimalism soft gate will flag
  them at runtime otherwise.
- **Every plan has a `## Research anchors` section.** If a plan
  legitimately had no prior research round (trivial fix, pure
  config tweak), the section still exists with one line saying
  so: `No research round — trivial fix, direct to plan.` This
  keeps the plan's evidence trail auditable and signals when a
  plan skipped research vs when it simply forgot the pointers.
- **Every plan has a `## Architectural posture` section.** It
  names the incumbent pattern (if any), states extend-or-redesign,
  and justifies the choice against the four architect dimensions.
  Trivial greenfield plans may say so in one line.
- **Phase anchors cite finding IDs, not file paths.** A phase's
  `Anchors.` line says `CODE-03, RISK-01` — the reader resolves
  those against the research JSONs in the anchors section.
