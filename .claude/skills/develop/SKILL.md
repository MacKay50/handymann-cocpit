---
name: develop
description: Use when the user says "plan", "design", "implement", "build a feature", "tackle this ticket", "work on Y", or when a change is non-trivial (over ~50 LoC or touches a high-stakes path). Workflow rails (Research → Plan → Implement → Review) for non-trivial changes — prefer over ad-hoc coding.
license: MIT
compatibility: opencode
metadata:
  audience: develop-conductor
  workflow: research-plan-implement-review
---

# Develop — Research → Plan → Implement → Review

Front-load the thinking so implementation is mechanical, and verify
each step before proceeding so bugs caught at the plan stage never
reach the code. Researchers and reviewers are scaled to the
problem's complexity (usually 1-3 each), each loading the relevant
concern-skills.

## Three tiers, three paths

The conductor classifies the change first (Stage 0 in
`develop-conductor.md`). The right path depends on the tier:

| Tier | Signals | Path |
|---|---|---|
| **trivial** | <50 LoC; 1 file or doc/comment; no high-stakes path | Defer to built-in `build`. No research, no plan, no subagents. See `AGENTS.md` §"Simple-change workflow". |
| **standard** | 50-300 LoC; 1-2 files; single subsystem; same exclusions as trivial; no new contract change | **Compressed RPIR** (see below). |
| **complex** | multi-subsystem, high-stakes path, schema/migration, new public surface, or anything else | Full RPIR, stages 1-4 below. |

Borderline cases resolve **up** (more discipline, not less). If
you can't tell trivial from standard, pick standard. If you can't
tell standard from complex, pick complex.

## Compressed RPIR (standard tier)

Single-phase path that keeps the rails without the overhead:

1. **One researcher** loaded with every relevant concern-skill (not
   split across two researchers). Still writes a JSON artifact
   under `research/<slug>/`. Conductor synthesises as normal; the
   brief is shorter because there's only one JSON to consume.
2. **Single-phase plan.** Planner produces a one-phase plan — no
   phase decomposition, because the change fits inside one commit
   boundary. `plan-verifier` still runs (sanity-checks anchors +
   acceptance criteria + subtraction check + architectural
   posture).
3. **One implementer + phase-verifier cycle.** The phase-verifier's
   deep review IS the review for the whole change.
4. **No stage 4.** Skipped — deep review already happened at phase
   boundary. Cross-phase integration drift is impossible with one
   phase.

User approval gates remain: research→plan, plan→implement,
phase→done. **Three stage boundaries, not four.** Three subagents
spawned, not six.

Re-route up to full RPIR if mid-compressed-flow you discover the
change actually touches complex-tier surfaces — stop, ask the user,
restart at Stage 1 with 2+ researchers.

## Full RPIR (complex tier)

```
Research → (conductor synthesis, may ask user) → Plan → Plan-verify
   ↓
Phase 1: Implement → Phase-verify → user approves → ...
   ↓
Phase N: Implement → Phase-verify → user approves
   ↓
Review (via `review` skill) → Ship
```

Each arrow is a checkpoint. The user approves progression.

---

## Stage 1 — Research

**Goal:** evidence to plan well. *Not* solutions (except via the
options concern, which is explicitly prescriptive). Research
artifacts land on disk under `research/<slug>/` so the plan can
reference them by path and downstream stages can resolve finding
IDs back to the original evidence.

### Step 0: Mint the slug and the research round directory

Before spawning anything, the conductor:

1. Mints a slug: `<YYYY-MM-DD>-<kebab-case-3-to-6-words>`. Reuse
   across a day → append `-v2`.
2. Creates the directory: `mkdir -p research/<slug>`.
3. Writes `research/<slug>/meta.json` with `slug`, `created`,
   `problem`, planned researcher list, eventual plan path
   (`plans/<slug>.md`), and `status: spawning`. See
   `references/research-schema.md` for the schema.

The slug ties research and plan together. Researchers write under
`research/<slug>/`; the planner writes `plans/<slug>.md` citing
those artifacts. The `research/` directory is gitignored — evidence
is regenerable and often quotes private data. The plan committed
to `plans/` carries the anchors; the evidence stays local.

### Step 1: Scope & researcher assignment

In your first reply:

1. **Problem statement.** One paragraph. Ask one clarifying
   question if needed, then proceed.
2. **Scale.** Pick the researcher count by problem shape:

| Problem | Researchers |
|---|---|
| Single-file fix or tweak | **1** |
| Single-subsystem feature | **1** |
| Cross-subsystem feature, refactor, or migration | **2** |
| Greenfield design or major architectural change | **3** |

3. **Concern assignment.** Pick concerns per researcher:

| Problem shape | Default concerns |
|---|---|
| New feature | code, contract, impact, options, risk (split across 2-3 researchers) |
| Refactor / migration | code, contract, impact, risk |
| Bug fix (non-trivial) | code, contract, risk |
| Config / infra change | code, impact, risk |
| Performance / scale | code, impact, options, risk |
| Spike / exploration | code, options |

For 1 researcher, load all relevant concerns onto it. For 2+,
split naturally:
- **Researcher A:** code + contract (the "what's there" pair).
- **Researcher B:** impact + risk (the "what could go wrong" pair).
- **Researcher C** (if 3): options (the prescriptive lane stands
  alone).

### Step 2: Domain-skill assignment

For each researcher, also assign relevant domain skills (per your
`AGENTS.md`).

### Step 3: Fan-out

Spawn each researcher (the generic `researcher` subagent) **in the
same turn**, parallel. Pass the slug and index so each researcher
writes to the right filename. Prompt template lives in
`references/workflow.md`.

### Step 4: Synthesise (conductor does this)

No separate research-judge subagent. The conductor (you) synthesises:

1. **Read each researcher JSON from disk** (the receipt named the
   path; don't rely on chat).
2. **Validate** each JSON against the schema.
3. **Deduplicate** findings across researchers; merge cross-concern
   hits (concordance is signal).
4. Surface decision points the planner will face.
5. **Pause and ask the user** when:
   - Researchers contradict each other on a fact.
   - A risk is high but mitigation is unclear from the citation.
   - The options researcher proposed N options but you can't tell
     which fit the user's actual constraints.
   - Frame specific choices, not "what do you think?".
6. **Write `research/<slug>/brief.md`** — the synthesised brief. It has:
   - Summary (3-6 sentences).
   - Key evidence (grouped by topic, citing finding IDs from the
     researcher JSONs).
   - Decision points (ordered).
   - Open questions resolved with user (if any).
   - Risk highlights.
   - Options to evaluate (from options researcher).
7. **Update `research/<slug>/meta.json`** to `status: synthesised`.
8. Present the brief path to the user; they may `cat` or read it
   in-chat. User approves "proceed to plan".

---

## Stage 2 — Plan

Spawn `planner` with the research slug and the path to the
synthesised brief. The planner reads every artifact under
`research/<slug>/` itself — the conductor doesn't paste findings
into the prompt; the planner walks the directory.

The planner loads `code-minimalism` and, for every proposed phase,
answers the subtraction check: is there a version of this phase
that achieves the goal by deletion rather than addition? Each
phase names explicit deletions (may be empty, but pure-addition
phases are flagged for the user's attention).

**The plan is persisted as a markdown artifact** at
`plans/<slug>.md` — the slug matches the research directory.

**The plan opens with a `## Research anchors` section** listing
every file under `research/<slug>/` with a one-line summary.
Individual phases cite specific finding IDs (`CODE-03`, `RISK-01`,
`OPT-B`) via an **Anchors** line. See `references/plan-schema.md`
for the template.

Spawn `plan-verifier` with the **path** to the plan file. It reads
the artifact directly (not from agent messages) and applies its
checks, including "every phase's Anchors line resolves to a
finding in the research artifacts".

The plan-verifier returns `APPROVED` or `NEEDS REVISION`. On
revision, the planner edits the same file in place. On approved,
**conductor pauses and asks the user about any plan-time
ambiguity** before presenting.

User approves "start phase 1".

---

## Stage 3 — Implement (one phase at a time)

For each phase:

1. **Spawn `implementer`** with the approved plan and the specific
   phase. It executes only that phase, TDD-first, loading
   `code-minimalism`, `test-driven-development`, and
   `systematic-debugging` as relevant. Report shape: short — files
   changed, Deletions, per-criterion met/partial, follow-ups,
   deviation proposals. Gate values are the phase-verifier's
   authority.
2. **Spawn `phase-verifier`** with the implementation. The
   phase-verifier is **not just a verifier** — it is a phase-scoped
   reviewer. It does two passes in one agent:
   - **Verification pass:** every acceptance criterion met with
     evidence; scope check; TDD check; minimalism soft gate.
   - **Review pass:** loads `code-minimalism` plus the concern-skills
     matched to what this phase touched, applies them to the phase
     diff, emits `SEC-`/`VIS-`/`REL-`/`DAT-`/`OPS-`/`MIN-` findings.
   The verdict combines both passes: `PASS`, `PASS WITH FOLLOWUP`,
   or `FAIL`. **Any critical or high finding FAILs the phase** —
   tracking a follow-up doesn't downgrade severity.
3. **Conductor synthesises, commits (when clean), and reports.**
   - **PASS (clean)** — no critical/high, no medium, no
     subtraction warning, no outstanding `ambiguity_questions`,
     secrets check clean. Conductor **auto-commits** the phase.
     Then asks "proceed to phase N+1 or pause?"
   - **PASS WITH FOLLOWUP** — acceptance met but medium findings
     exist. Conductor does **not** auto-commit. Presents findings;
     user decides: commit as-is + track, fix now, or split into a
     follow-up phase.
   - **FAIL** — never commit. Conductor loops implementer (small
     issue, clear fix) or escalates to user (structural,
     contested, critical). Critical always escalates.

   Auto-commit keeps phase boundaries on the git history and
   makes `git bisect` useful.
4. **On ambiguity**, conductor asks the user — including the
   phase-verifier's own `ambiguity_questions` array. Frame
   specific options; never silently pick a side.

Why deep review per phase: the phase diff is small, fresh, and
in context. Catching vision drift, security issues, and bloat
here is near-free. Saving them up for stage 4 means re-opening
phases that may already be partially merged.

---

## Stage 4 — Cross-phase integration review

Per-phase reviews (stage 3) already caught per-partition issues
as they landed. Stage 4 is the **cross-phase integration pass** —
looking at the whole change as a gestalt:

- **Coherence across phases.** Did phase 2 and phase 4 introduce
  overlapping vocabulary, parallel implementations, or redundant
  helpers that looked fine in isolation but duplicate each other?
- **Full-diff minimalism.** A subtraction audit across the whole
  change.
- **Release-readiness signals.** Do migrations + code + config
  deploy atomically? Is the deploy values file aligned?
- **Vision drift in aggregate.** A new concept that snuck in
  across two phases that no single per-phase review flagged.

**Before invoking the `review` skill**, run the pre-merge
verification recipe (unit tests; integration smoke; UI build if
UI touched). Broken builds waste review cycles.

Then invoke the `review` skill on `git diff <base>...HEAD`.
Because the per-phase reviews already happened, stage 4 typically
runs with **fewer reviewers** than it would cold — often 1
cross-cutting reviewer with `review-vision-concerns` +
`review-operations-concerns` + `code-minimalism` loaded.

Verdict handling:
- `SHIP` → user merges/pushes.
- `SHIP WITH FOLLOWUP` → user files follow-ups, then ships.
- `DO NOT SHIP` → fix; if structural, return to stage 2.
- `BLOCKED` → resolve scope issue, re-run review.

---

## Hard rules

1. **No stage skipping.** "Just implement" on a non-trivial change
   is how vision-violating code ships.
2. **No implementer before plan approval.** User approves, not
   verifier.
3. **No phase merging.** Separate phases stay separate.
4. **Read-only stages stay read-only.** Researcher, planner,
   plan-verifier, phase-verifier — all read-only on source.
   Implementer is the only write-source agent.
5. **Every stage ends at the user.** Conductor produces artefacts;
   humans approve progression.
6. **Use the `review` skill for the final gate.** Do not
   reimplement review here.
7. **Cite or it's noise.**
8. **Ask the user on ambiguity.** Conductor pauses, frames options,
   records resolution. Never silently picks a side.

---

## Quick reference — what to say to the user at each stage boundary

- **Start of research:** "Problem: X. Spawning N researcher(s)
  with concerns [list] and domain skills [list]." Then run.
- **End of research:** "Research brief at <path>. Decision points:
  [list]. Open questions resolved: [list]. Proceed to plan?"
- **End of plan:** "Plan at <path>, verifier APPROVED. N phases.
  Anything to change before phase 1?"
- **End of each phase (clean PASS):** "Phase N PASS, committed as
  `<sha>`: <subject>. Net LoC: [+X / -Y]. Findings: none. Proceed
  to N+1 or pause?"
- **End of each phase (PASS WITH FOLLOWUP):** "Phase N PASS with
  N medium findings — [list]. Not committed yet. Commit as-is
  and track, fix now, or split into a follow-up phase?"
- **End of implementation:** "All phases PASS. Running review."
- **End of review:** report verdict; user decides next.

---

## Further reading

- `references/research-schema.md` — JSON shape from each researcher.
- `references/plan-schema.md` — the plan template the planner produces.
- `references/workflow.md` — prompt templates for each subagent.
