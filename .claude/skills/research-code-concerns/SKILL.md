---
name: research-code-concerns
description: Use when a researcher needs a code-reachability map of a slice before planning — entry points, call graph, data flow, test coverage, similar patterns. Descriptive only, no solutions.
license: MIT
compatibility: opencode
metadata:
  audience: researcher
  workflow: develop
---

You are researching this slice for code reachability. You produce a
**reachability map**: for the problem at hand, which code is in
the blast radius? Purely descriptive. Do not propose solutions —
that's a planner concern.

## Required reading

- `AGENTS.md` §Repository layout
- Any file/path the problem statement points at

## What to produce

For the problem, find and cite:

1. **Entry points.** Where does the feature/behaviour enter the
   system? API endpoint? Pipeline stage? Handler?
2. **Call graph.** From each entry point, what functions are
   called, where, with what signatures? Trace 2-3 levels deep;
   more if the chain is load-bearing.
3. **Data flow.** Which variables flow from the entry point to
   the decision point? Where are they validated, transformed,
   persisted?
4. **Tests.** Which tests cover the current code? What branches
   do they exercise? What branches don't they exercise?
5. **Related code nearby.** Files in the same directory that
   share concerns — useful for the planner to know about
   cross-cutting.
6. **Similar patterns elsewhere.** If the problem looks like
   something the repo already solved, cite the precedent.

## Red flags to surface

- Function with no tests at all.
- Dead code (function not called from anywhere).
- Duplicated logic across files.
- Comment out-of-date with code.
- A branch that looks unreachable but isn't.

These become findings with clear `relevance` explaining why the
planner cares.

## Decision points to list

Typical decision points this concern surfaces:

- "The entry point currently lives in X; the planner has to decide
  whether to modify X or wrap it."
- "There are two call sites of the helper; the planner has to
  decide whether to refactor both or introduce a new helper."
- "Tests cover branches A/B but not C; the planner has to decide
  whether to add C-coverage as part of this work or as a follow-up."

## What NOT to do

- Don't propose a solution. "I recommend doing X" is out of scope —
  that's the `research-options-concerns` skill's domain.
- Don't speculate about code you didn't read. Cite file:line.
- Don't widen scope speculatively.
- Don't pass judgement on code quality. That's a review-time concern.
- Don't produce a "summary of the file" — produce a map relevant
  to the problem.
