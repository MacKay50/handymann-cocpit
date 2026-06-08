---
name: review-data-concerns
description: Use when reviewing a slice that touches models, schema, migrations, external system clients, business policy, admin API, or anywhere data shapes flow across layers. Checks shape parity, schema invariants, migration safety, output contracts.
license: MIT
compatibility: opencode
metadata:
  audience: reviewer, phase-verifier
  workflow: review
---

You are reviewing this slice for **data concerns** — the shapes of
data flowing through the system, and whether the change preserves
their integrity. Findings get the `DAT-` prefix.

## Required reading

- `AGENTS.md` §Tech stack (data layers)
- The schema files (`init.sql`, migrations, Prisma schema, etc.)
- Type definitions (Pydantic models, TypeScript types, Zod schemas)
- The slice itself

## What to scan for

### Shape parity across layers

- **Backend ↔ frontend type drift.** The backend serialises a
  field as `string`; the frontend type expects `number`. Silent
  parsing somewhere; possible round-trip data loss.
- **Internal ↔ external system drift.** Code treats an external
  ID as int; external system returns string with leading zeros.
  Coercion loses information.
- **Migration ↔ code drift.** Code references a column that's not
  in the canonical schema, or references the new column but the
  migration is in a separate phase.

### Schema integrity

- **Wrong column type.** `text` where `varchar(N)` was needed;
  `int` where `bigint` was needed; `float` where `decimal` was
  needed (financial fields).
- **Missing constraint.** No `NOT NULL` on a field the code
  assumes is non-null; no `UNIQUE` on a field the code uses as a
  natural key.
- **Missing index.** A query path that scans on a large table.
- **Cascade semantics.** `ON DELETE CASCADE` on a parent table
  with audit-relevant children — accidentally deletes audit rows.

### Migration safety

- **Forward-incompatible migration.** Old code can't read new
  data; rolling back requires reverting data too.
- **Backward-incompatible migration.** New code can't read old
  data; rollout window has a broken state.
- **Long-running migration in a deploy.** Locks tables; downtime
  during deploy.
- **Data loss in migration.** Drops a column with active data
  without a backfill plan.

### Output contracts

- **LLM output JSON shape.** Code asks the LLM for fields A/B/C
  but reads field D. Or asks for a list and reads as object.
- **Missing-field handling.** Code does `parsed.get("amount")`
  with no else-branch — masking fallback (also `code-minimalism`
  §3).
- **Type assumption.** Code assumes the LLM returned a number; in
  practice it returns "42" as a string sometimes.

### External system pitfalls (if applicable)

- **String vs int IDs.** Many systems use string IDs that look
  like numbers; coercing to int loses leading zeros and prefix
  letters.
- **Tombstones.** Soft-deleted rows that look live to a naive
  query.
- **Date/time formats.** Systems with ambiguous date formats; UTC
  vs local; ISO vs custom.
- **Encoding.** Latin-1 columns; UTF-8 surrogates; emoji
  truncation.

## Severity calibration

| Finding | Severity |
|---|---|
| Shape parity drift on a financial / auth / audit field | critical |
| Shape parity drift on any other field | high |
| Forward-incompatible migration without rollout plan | high |
| Backward-incompatible migration without rollout plan | high |
| Wrong column type for the data it stores | high |
| Code reads a field the LLM wasn't asked for | high |
| Missing-field handling (masking fallback) | high (per code-minimalism §3) |
| Missing constraint on a field code assumes constraint exists | medium |
| Missing index on a known-hot query path | medium |
| Inconsistent type coercion in different code paths | low |

## What `cleared[]` to populate

- "Verified shape parity at file:line — backend type and frontend
  type both `customer_id: string`."
- "Verified migration is forward-compatible at <migration-file> —
  old code can read new data."
- "Verified LLM output schema validation at file:line — required
  fields enforced before use."

## Anti-examples

- "Schema looks weird" — vague. Cite the column and the concrete
  problem.
- "Could break with bad data" — what data? what failure?
- "Should add validation" — where, on what?
