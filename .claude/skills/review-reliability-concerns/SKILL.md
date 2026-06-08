---
name: review-reliability-concerns
description: Use when reviewing a slice that touches the pipeline, agents, external clients, business logic, or any I/O boundary. Checks timeouts, fail-safe on errors, idempotency, circuit-breaker, branch coverage, partial-failure modes.
license: MIT
compatibility: opencode
metadata:
  audience: reviewer, phase-verifier
  workflow: review
---

You are reviewing this slice for **reliability concerns**. What
breaks when the world misbehaves? Findings get the `REL-` prefix.

This is the lens that imagines production: the slow database, the
flaky external service, the malformed payload, the duplicate
request, the partial failure.

## Required reading

- `vision.md` §Fail-safe (or equivalent)
- `code-minimalism` §3 "Masking fallbacks" — load if not already loaded
- The slice itself

## What to scan for

### External I/O

- **No timeout.** A call that can hang forever blocks the caller
  forever.
- **No retry strategy.** Transient failures should retry; permanent
  failures shouldn't. Often the same code does neither correctly.
- **No idempotency.** Retries on writes corrupt data unless writes
  are idempotent or guarded.
- **No bounded fetch.** Streaming a response with no size cap
  invites OOM under attack.

### Error handling

- **Masking fallbacks.** Per `code-minimalism` §3 — silent default
  on failed I/O. **High** by default; **critical** on high-stakes
  paths.
- **Broad except.** `except Exception:` (or equivalent in your
  language) without specifically handling and re-raising or
  escalating loud. Catches errors you didn't anticipate; hides
  bugs.
- **Swallowed exceptions.** `try/except: pass` — the worst form of
  the above.
- **Wrong escalation surface.** Error caught in the wrong layer —
  either too low (loses context) or too high (loses precision).

### State integrity

- **Race conditions.** Concurrent writes to the same row, the same
  cache key, the same file. Especially when there's no lock.
- **Partial-write failure.** Step 1 succeeds, step 2 fails;
  database is in an inconsistent state.
- **Stale reads.** Cached data with a TTL longer than the
  underlying data's update frequency.
- **State leaks across requests.** Module-level mutable state, a
  long-lived client with shared mutable config.

### Branch coverage

- **The error branch isn't tested.** Tests cover the happy path
  but not the failure path. The failure path is where bugs hide.
- **The boundary case isn't tested.** Empty list, max value, off-
  by-one. Especially for new branches in this slice.

### Circuit-breaker / rate-limiting

- **No circuit breaker on a flapping dependency.** An external
  service with sometimes-30%-error rate will eventually take down
  this caller without a breaker.
- **No rate limit on outbound calls.** A single user can amplify
  the system into a DoS against a downstream.

## Severity calibration

| Finding | Severity |
|---|---|
| Masking fallback on high-stakes path | critical |
| Masking fallback on any other path | high |
| No timeout on external I/O | high |
| Broad except / swallowed exception in core flow | high |
| Race condition in business logic | high |
| Missing test for new error branch | medium |
| Missing test for boundary case | medium |
| No retry on a known-flaky dependency | medium |
| Stale-read tolerance not documented | low |
| Logging doesn't include enough context for debugging | low |

## What `cleared[]` to populate

- "Verified timeout at file:line — `client.get(timeout=5)`."
- "Verified failed-I/O escalates at file:line — `except FooError:
  escalate(...)`, not silent default."
- "Verified idempotent write at file:line — uses upsert with
  unique key."

## Anti-examples

- "Could be a race" — cite a specific scenario or drop.
- "Should add a retry" — to what? On what trigger? Cite the call
  site.
- "Error handling is sloppy" — vague. Either cite the specific
  pattern or drop.
