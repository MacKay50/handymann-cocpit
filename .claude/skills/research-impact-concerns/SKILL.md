---
name: research-impact-concerns
description: Use when a researcher needs to understand what else moves if this moves — blast radius across services, deployment dependencies, cross-version compatibility, downstream consumers. Descriptive.
license: MIT
compatibility: opencode
metadata:
  audience: researcher
  workflow: develop
---

You are researching the **blast radius** for this slice. What
other parts of the system, deployment, or external consumers move
when this moves? Purely descriptive.

## Required reading

- `AGENTS.md` §What this repo is + §Tech stack (the planes)
- Deployment manifests (Helm values, Terraform, docker-compose)
- CI workflows (`.github/workflows/`)
- The problem statement

## What to map

For the problem, find and cite:

1. **Cross-service impact.** If the change is in service A, what
   does service B do that depends on A? An API contract change,
   a shared schema, a queue topic.
2. **Frontend-backend coordination.** If the backend changes
   shape, does the frontend need a coordinated deploy? Can they
   roll out independently? In which order?
3. **Deployment artifacts.** Helm values that need updating,
   Terraform variables, environment variables, secrets, ConfigMaps.
4. **External consumers.** Anyone reading this system's output
   (downstream services, dashboards, exports, replicas). Will
   they tolerate the change?
5. **CI/CD pipeline.** Does the change require new build steps,
   new test fixtures, new credentials in CI?
6. **Data migrations.** If schema changes, what's the migration
   path? Forward-compatible? Backward-compatible? Both?
7. **Rollback feasibility.** If we ship and need to roll back,
   what does that look like? Is the change reversible? Does
   rolling back require a coordinated effort?

## Red flags to surface

- **Coordinated-deploy required.** Two services have to ship
  together or in a specific order — names the orchestration risk.
- **Forward-incompatible migration.** Old code can't read new
  data; means rollback requires reverting data too.
- **Silent consumer.** Something reads the system's output that
  isn't in the obvious list — a metrics dashboard, an export
  job, an LLM training pipeline.
- **CI dependency change.** New tool, new credential, new build
  artifact required. CI may break before the deploy.

## Decision points to list

- "Does the rollout require a feature flag? Single-deploy or
  staged?"
- "Does the migration need to run before, during, or after the
  code deploy?"
- "Is there a downstream consumer we should notify?"

## What NOT to do

- Don't propose deployment plans — describe what the deployment
  will need to handle.
- Don't speculate about consumers you can't cite — only flag
  consumers you can find evidence of.
- Don't grade rollout strategies; that's planner-level.
