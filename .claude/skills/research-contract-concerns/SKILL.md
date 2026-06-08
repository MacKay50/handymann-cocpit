---
name: research-contract-concerns
description: Use when a researcher needs to map the shape of data and APIs touched by a problem — request/response models, database schema, internal APIs, frontend types, config keys, external system field shapes. Descriptive only.
license: MIT
compatibility: opencode
metadata:
  audience: researcher
  workflow: develop
---

You are researching the **contract surface** for this slice. The
shapes of data, APIs, schemas, config keys, and types that the
change will touch or be touched by. Purely descriptive.

## Required reading

- `AGENTS.md` §Tech stack (what data layers exist)
- The problem statement
- Any contract docs (`docs/api.md`, OpenAPI specs, schema files)

## What to map

For the problem, find and cite:

1. **Request / response models.** Pydantic, Zod, JSON Schema,
   protobuf, GraphQL types. The shapes that flow in and out of
   the affected surface.
2. **Database schema.** Tables, columns, types, nullability,
   constraints, indexes that the change touches. Note recent
   migrations.
3. **External system contracts.** If the slice integrates with an
   external API/database/IdP/etc., map the fields used. Watch
   for assumptions about types (string vs int, padding,
   timezones).
4. **Config keys.** Keys read by the code in scope. Where are they
   defined? Where are they validated? What are the defaults?
5. **Frontend types** (if applicable). TypeScript / GraphQL types
   that mirror backend shapes. Drift between frontend and backend
   is a common source of bugs.
6. **Output contracts the LLM is asked for** (if the slice uses an
   LLM). The expected JSON shape; what happens on missing fields.

## Red flags to surface

- **Shape parity drift.** Backend says `customer_id: string`,
  frontend says `customer_id: number` — silent integer parsing
  somewhere.
- **Optional vs required mismatches.** Schema says NOT NULL, code
  has a default.
- **Type coercion.** External system returns strings, internal code
  treats as int (or vice versa). Especially for IDs.
- **Unbounded fields.** Free text columns with no length cap;
  potential abuse vector.
- **Missing migration.** Code references a column that doesn't
  exist in the canonical schema, or references the *new* column
  but the migration is in a different commit.

These become findings with `relevance` explaining why the planner
cares.

## Decision points to list

- "The request model currently has X; should the new field be
  required, optional with default Y, or optional with `null`?"
- "The frontend type lives separately from the backend; the
  planner must update both or use a code-gen pipeline."
- "External system column is `varchar(20)`; should we match
  exactly or add validation?"

## What NOT to do

- Don't propose schema changes — describe the current shape.
- Don't widen the contract surface beyond what the problem
  touches.
- Don't pass judgement ("this schema is bad"); cite the shape
  with `relevance` and let the planner decide.
- Don't run database queries unless the schema doc is wrong; the
  schema file in the repo is the canonical source.
