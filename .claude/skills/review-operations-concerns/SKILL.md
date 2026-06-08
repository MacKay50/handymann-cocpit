---
name: review-operations-concerns
description: Use when reviewing a slice that touches admin endpoints, deploy values, schema, metrics/tracing, or anything affecting how the system is run in production. Checks audit-row completeness, rollout controls, observability layers, health/readiness, config hot-reload, migration safety, rollback realism.
license: MIT
compatibility: opencode
metadata:
  audience: reviewer, phase-verifier
  workflow: review
---

You are reviewing this slice for **operations concerns**. Can the
people who run this system in production diagnose, control, and
recover from problems with this change? Findings get the `OPS-`
prefix.

## Required reading

- `AGENTS.md` §How to build and run, §How to test, §any auth /
  deploy / monitoring sections
- Deployment manifests (Helm values, Terraform, docker-compose)
- The slice itself

## What to scan for

### Audit / mutation trail

- **Missing audit row.** A mutation (config change, role grant,
  policy update) that doesn't write to the audit table.
- **Audit row missing fields.** Audit row exists but doesn't
  capture *who*, *when*, *what changed from/to*, *reason* given
  by the operator.
- **Reason field unenforced.** Mutation ConfirmDialog/UI has a
  reason textarea but the backend doesn't require it.

### Observability

- **Missing metric.** Important state change with no metric
  counter / gauge / histogram. Hard to alert on what you can't
  measure.
- **Missing trace span.** A request flow that crosses async/queue
  boundaries with no correlation ID — debugging is forensic.
- **Missing log line.** An error path with no log; ops will see
  the symptom but not the cause.
- **Log line missing context.** A log without correlation ID,
  user identity, or request shape; not useful for debugging.

### Health / readiness

- **Health endpoint doesn't reflect actual health.** Returns 200
  while a critical dependency is down.
- **Readiness probe doesn't gate startup.** Container marked
  ready before it can actually serve.
- **Liveness probe causes restart loops.** Probe is too strict;
  pod restarts on transient blips.

### Rollout control

- **No feature flag for a risky change.** A change that needs
  staged rollout has none.
- **No traffic gate.** The change is on for 100% of users on
  deploy; no way to limit blast radius.
- **No kill switch.** Operator has no way to disable the new
  behaviour without a deploy.

### Configuration

- **Hot-reload missing.** Operator has to restart to change a
  knob; in production this means a deploy window.
- **Config validation missing.** Invalid config silently accepted;
  manifests as runtime errors later.
- **Config drift across environments.** Dev / staging / prod have
  different values for a key that should be the same shape.

### Migration / deploy safety

- **Migration not idempotent.** Running it twice corrupts data.
- **Migration can't be rolled back.** Once run, no path back.
- **Deploy requires manual step.** "Run this command after deploy"
  documented somewhere — guaranteed to be missed.
- **Deploy depends on order.** Service A must roll out before
  service B; not enforced anywhere.

## Severity calibration

| Finding | Severity |
|---|---|
| Missing audit row on a high-stakes mutation | critical |
| Missing audit row on any other mutation | high |
| Health endpoint returns 200 while broken | high |
| No feature flag on a risky high-stakes change | high |
| Migration that can't be rolled back without explicit plan | high |
| Missing metric on a state change worth alerting on | medium |
| Missing trace span on an async boundary | medium |
| Missing kill switch on new behaviour | medium |
| Log line missing correlation ID | low |
| Config inconsistent across environments | low |

## What `cleared[]` to populate

- "Verified audit row at file:line — captures user, timestamp,
  before/after, reason."
- "Verified metric counter at file:line — `<counter_name>` with
  labels matching alerting query."
- "Verified rollback runbook at <doc-file> — migration reverts
  cleanly without data loss."

## Anti-examples

- "Should add monitoring" — what monitoring? for what? cite the
  call site that needs visibility.
- "Audit might be missing" — verify and either cite the gap or
  put it in `cleared[]`.
- "Deploy is risky" — any deploy is risky. Cite the specific
  failure mode.
