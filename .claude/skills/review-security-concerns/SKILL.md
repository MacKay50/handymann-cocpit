---
name: review-security-concerns
description: Use when reviewing a slice that touches admin endpoints, auth, user input, the LLM trust boundary, database queries, outbound HTTP, the frontend fetch surface, or anything secret-adjacent. Project-specific security checklist.
license: MIT
compatibility: opencode
metadata:
  audience: reviewer, phase-verifier
  workflow: review
---

You are reviewing this slice for **security concerns**. Findings
get the `SEC-` prefix. Pair with `owasp-security` for the
canonical OWASP lens (not shipped in the starter; add when needed).

## Required reading

- `vision.md` §any security/PII principles
- `AGENTS.md` §Auth model
- The slice itself

## What to scan for

### Input handling

- **Validation gap.** External input (HTTP body, query params,
  headers) reaches business logic without bounds/format/type checks.
- **Trust boundary leak.** Data from a less-trusted source flows
  into a more-trusted context without re-validation.
- **Injection vectors.** Unparameterised SQL, shell commands built
  with f-strings, HTML rendered from user-controlled strings.

### Auth / authz

- **Missing auth check.** Endpoint reachable without a verified
  identity.
- **Missing role check.** Endpoint reachable by any authenticated
  user when only some should access it.
- **Privilege escalation paths.** Lower role can write data the
  higher role reads.
- **Token handling.** JWTs validated server-side? Token leaks via
  logs, error responses, or query strings?

### Data leakage

- **PII in logs.** Sensitive fields in log lines, error messages,
  or trace spans.
- **PII to LLM.** Sensitive fields reaching the LLM prompt without
  redaction.
- **PII to external system.** Sensitive fields in outbound HTTP /
  database writes.
- **Secrets in committed files.** Already gated by phase-verifier
  Gate 1, but flag any near-misses (e.g., `.env.example` with a
  real-looking secret).

### LLM trust boundary

- **Prompt injection.** User-controlled text reaches LLM prompts
  without sanitisation.
- **LLM output trust.** LLM output is acted on as if it were
  validated data — without bounds/format/type checks downstream.
- **Tool use risks.** LLM has access to tools (functions, MCP
  servers) that can be misused via prompt injection.

### Outbound surface

- **SSRF.** User-controlled URLs reach `requests.get(...)`.
- **Unsafe deserialisation.** `pickle.loads`, `yaml.load` without
  safe variants on untrusted input.
- **Unbounded fetches.** No timeout, no size cap on downloaded
  content.

## Severity calibration

| Finding | Severity |
|---|---|
| Secret committed | critical (also Gate 1) |
| Auth check missing on a write endpoint | critical |
| Auth check missing on a read endpoint | high |
| PII in logs | high |
| PII to LLM | high (critical if your project's vision invariants forbid it) |
| Unparameterised SQL | high (critical if user-controlled) |
| Prompt injection vector | high |
| SSRF / unsafe deserialisation | high |
| Missing timeout on outbound HTTP | medium |
| Validation missing on a non-auth-touching field | medium |
| Logs include correlation ID without sanitisation | low |

## What `cleared[]` to populate

- "Verified auth check at file:line covers route X."
- "Verified PII redaction at file:line runs before LLM call."
- "Verified parameterised query at file:line."

The `cleared[]` array is how the conductor knows the surface was
covered.

## Anti-examples

- "Could be a security issue" — no specific failure mode. Drop or
  raise as `confidence: low`.
- "PII might leak" — cite where. If you can't cite, it's not a
  finding.
- "Should probably add a timeout" — without a specific call site,
  it's a `MIN-low` cleanup, not a SEC finding.
