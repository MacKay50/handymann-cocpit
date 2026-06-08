# phase-verifier rubric — gate commands + finding map

Runnable spec the phase-verifier executes against. Each gate below
documents the exact command(s) to run, how to interpret the output,
and how to map results to findings.

> **Customise this file for your stack.** The placeholders
> (`<LINTER_CMD>`, `<TESTRUNNER_CMD>`, `<UI_LINT_CMD>`, etc.) are
> deliberately language-neutral. Replace them with your project's
> actual commands. See `ADOPTION.md` §"Step 4 — adapt the
> phase-verifier gates" for the customisation checklist.

Loaded from `phase-verifier.md` when running Pass 1 mechanical
checks.

## Scope establishment (run this first)

Before any gate runs, establish the pathspec list the phase is
allowed to touch. The plan's per-phase `Files` block is the
authoritative source.

```bash
# Read the phase's declared scope from the plan
grep -A 40 "^### Phase <N>:" plans/<slug>.md \
  | awk '/^\*\*Files\.\*\*/,/^\*\*Dependencies/' \
  | sed -n '/^```/,/^```/p' | grep -v '^```'
```

The output is the scope pathspec list. Every gate below is
**filtered by this scope** — unrelated in-flight work outside the
phase's declared paths is invisible to the gate by design.

If the plan has no explicit Files/Scope block, STOP and ask the
conductor — don't run gates against the full working tree and
pretend the result is attributable to the phase.

## Gate 1 — Secrets scan

Purpose: no `.env`, credential, private-key, or secret-shaped
filename in the diff.

```bash
git diff --name-only <phase-base>..HEAD -- <scope-pathspecs> \
  | rg -iE '(\.env$|credentials\.json|private.*key|id_rsa|\.pem$|\.key$)'

git diff <phase-base>..HEAD -- <scope-pathspecs> \
  | rg -iE '(password|api[_.-]?key|secret|token|bearer)\s*[=:]\s*["\x27][^\s"\x27]{8,}'
```

**Interpretation:**

- Empty output on both → emit `**Secrets check:** clean` in
  Section 1.
- Any hit → **critical** `scope_blocker` finding, FAIL the phase
  immediately. Emit `**Secrets check:** flagged: <paths/matches>`.
  Do not proceed to further gates; the conductor must reject the
  phase before any other signal matters.

## Gate 2 — Lint ratchet (when phase touches language-relevant files)

> **Customise:** replace `<LINTER_CMD>` with your linter (pylint,
> eslint, golangci-lint, clippy, etc.) and `<SUBSTANCE_RULES>` with
> the rules you treat as "real correctness issues" (typically 5-10).

**Skip this gate entirely** when the phase touches no language files
the linter cares about:

```bash
git diff --name-only <phase-base>..HEAD -- <scope-pathspecs> \
  | rg '\.(py|ts|tsx|js|go|rs)$' || exit 0
```

Emit `**Lint:** n/a` and move on.

### Check 1 — Substance findings on net-new lines

```bash
# 1. Identify changed files in scope
CHANGED=$(git diff --name-only <phase-base>..HEAD -- <scope-pathspecs> \
  | rg '\.(py|ts|tsx|js|go|rs)$')

# 2. Run linter with structured (JSON) output on just those files
<LINTER_CMD> --output-format=json $CHANGED > /tmp/lint-phase.json

# 3. Identify net-new line ranges per file
for f in $CHANGED; do
  git diff --unified=0 <phase-base>..HEAD -- "$f" \
    | rg '^@@' \
    | sed -nE 's/^@@ -[0-9]+(,[0-9]+)? \+([0-9]+)(,([0-9]+))? @@.*/\2 \4/p' \
    > /tmp/new-lines-"$(basename "$f")".txt
done
```

**Substance rules to filter on** (project-specific — only these FAIL):

```
<SUBSTANCE_RULE_1>
<SUBSTANCE_RULE_2>
<SUBSTANCE_RULE_3>
...
```

(For pylint: `broad-exception-caught`, `bare-except`,
`unused-argument`, `unused-variable`, `unreachable`, `dead-code`,
`duplicate-code`. Map to your linter's rule names.)

**Interpretation:**

- For each linter finding in `/tmp/lint-phase.json`:
  - If its rule is in the substance list AND its `line` falls
    within a net-new range for that file → **high** finding,
    concern `minimalism` + relevant domain concern, id `MIN-<N>`,
    FAIL the phase.
  - If its rule is NOT in the substance list AND its `line` falls
    within a net-new range → **advisory**. Do NOT individually
    fail. Bundle advisories into at most one `MIN-low` or
    `MIN-medium` finding if they cluster. Drop silently if they
    don't cluster. NEVER emit one finding per advisory.

### Check 2 — Substance findings on touched lines

Same rule filter as Check 1. "Touched" = any line the phase
modified, whether net-new or a pre-existing line edited in place.

**Interpretation:** any substance finding on a touched line →
**high**, FAIL.

### Check 3 — Lint config drift

Diffed against the **plan base** (the commit the plan was authored
from), not just the phase base. Blocks two-phase attacks where
phase 1 weakens config and phase 2 ships code that only passes
under weakened rules.

```bash
# Locked keys in your linter config that require plan
# authorisation to change. Customise per your config file format.
LOCKED_KEYS='(fail-under|disable|ignore-paths|max-args|max-branches)'

git diff <plan-base>..HEAD -- <CONFIG_FILE> \
  | rg -E "^[+-]\s*($LOCKED_KEYS)\s*="
```

**Interpretation:**

- Empty output → emit `**Lint config drift:** none`.
- Any hit that is NOT explicitly authorised in the plan's phase
  narrative → **critical** finding, FAIL.
- A hit that IS authorised by the plan → emit it as a **medium**
  finding for visibility, do not FAIL.

### New `# noqa` / `// eslint-disable` / equivalent comments

```bash
git diff <phase-base>..HEAD -- <scope-pathspecs> \
  | rg '^\+.*(# noqa|# pylint:|// eslint-disable|#\[allow\()'
```

**Interpretation:**

- Line-local disable with specific per-line justification naming
  the false-positive mechanism → **low** `MIN-` finding
  (documented, accept).
- Vague justification (`# needed`, `# fine`, `# by design`) or no
  justification → **high** `MIN-` finding, FAIL. Reader cannot
  verify the justification against the actual code.

## Gate 3 — Cleanup completeness

Runs when the implementer's report has a non-empty `Deletions` list.

```bash
# For each token in the implementer's Deletions list:
for TOKEN in "$@"; do
  rg -n --fixed-strings "$TOKEN" -- <scope-pathspecs>
done
```

The implementer reports deletions in their markdown output. The
verifier extracts each token (function name, constant, config
key, action name, string literal, doc heading) and runs the rg
above.

**Interpretation:**

- Empty output for every token → emit `**Cleanup:** clean`.
- Any surviving reference (residual):
  - **High-stakes path** (per `AGENTS.md` §"Simple-change workflow"
    exclusions list) → **critical** `MIN-` finding. FAIL. Does NOT
    accept `PASS WITH FOLLOWUP`.
  - **Any other path** → **high** `MIN-` finding, FAIL.
  - **Exception:** plan's `Out of scope` section explicitly names
    the file/directory as deferred with an owning phase. Downgrade
    per plan. Silent deferral ("cosmetic follow-up") is not
    acceptable.

## Gate 4 — Net LoC + minimalism soft-warn

```bash
git diff --shortstat <phase-base>..HEAD -- <scope-pathspecs>
# Example output: "5 files changed, 127 insertions(+), 14 deletions(-)"
```

Compute `net_loc = insertions - deletions`.

**Interpretation:**

- Emit `**Minimalism:** ok (net +<N>, <M> deletions)` when net is
  modest or deletions are non-empty.
- **Soft-warn trigger:** `net_loc > +100` AND implementer's
  `Deletions` list is empty AND the plan did not pre-authorise
  pure addition. Emit `**Minimalism:** subtraction_warning (net
  +<N>, deletions empty)` and surface to the conductor via an
  `ambiguity_questions` entry. Not an automatic FAIL — conductor
  decides with the user.

## Gate 5 — Frontend lint (when phase touches UI files)

> **Customise:** replace `<UI_LINT_CMD>` with your UI lint+build
> command. Skip this gate entirely if your project has no UI.

Skip when no UI files in scope:

```bash
git diff --name-only <phase-base>..HEAD -- <scope-pathspecs> \
  | rg '^<ui-dir>/' || exit 0
```

Emit `**Frontend lint:** n/a` if nothing to check.

Otherwise:

```bash
<UI_LINT_CMD>
# e.g.: cd frontend && bun run lint && bun run build
```

**Interpretation:**

- Both exit 0 → emit `**Frontend lint:** clean`.
- `lint` fails → **high** finding, FAIL. Concern `ux` +
  `minimalism`.
- `build` fails (TypeScript error) → **high** finding, FAIL.
  Concern `ux` (type-level correctness is a UX invariant — the
  feature doesn't work).

## Gate 6 — Acceptance criteria

For each `[AC-N]` criterion in the plan's phase block, re-run the
verifiable command the plan names and confirm pass/fail yourself.

**Interpretation:**

- Every criterion met → emit `**Acceptance:** PASS`.
- Any criterion unmet → emit `**Acceptance:** FAIL` with specific
  criterion ID + observed vs expected. This is an automatic phase
  FAIL regardless of other gate outcomes.

Trust nothing the implementer's report claims about acceptance;
the implementer reports "met / partial" but the verifier runs the
command fresh.

## Gate 7 — Scope drift

```bash
# All paths in the diff
DIFF_PATHS=$(git diff --name-only <phase-base>..HEAD)

# Paths the phase declared (from the Files block)
DECLARED_PATHS=$(<extract from plan>)

# Anything in DIFF_PATHS not in DECLARED_PATHS is drift
comm -23 <(echo "$DIFF_PATHS" | sort) <(echo "$DECLARED_PATHS" | sort)
```

**Interpretation:**

- Empty output → emit `**Scope:** in-scope`.
- Any hit → **high** finding, FAIL. Concern `minimalism`. The
  implementer should have stopped and emitted a deviation
  proposal, not silently widened scope.

## What this rubric deliberately does NOT mechanize

These gates remain the phase-verifier's LLM-driven Pass 2 work:

- **TDD satisfaction.** Mechanical check is "tests exist in the
  diff"; real check is "tests exercise the new production code
  meaningfully and would fail if the implementation were wrong".
- **Scope justification.** The diff may legitimately be wider than
  the declared Files list (e.g., an unavoidable import update).
  The verifier judges whether the deviation is justified.
- **Fail-loud masking.** The linter catches `except Exception:`
  but NOT `parsed.get("amount", 0)`, `if x is None: x = default()`,
  or silent `return None` on external API errors. The verifier
  reads the diff and flags runtime defaults on high-stakes I/O
  per `code-minimalism` §3 "Fallbacks that mask the hot path".
- **Concern-based deep review (Pass 2).** Vision, reliability,
  security, data, operations findings — all loaded via
  concern-skills and applied by reading the diff.
- **Same-concept residuals when the implementer's Deletions list
  was incomplete.** If the implementer's report mentions a
  conceptual deletion but didn't enumerate every token, the
  verifier should grep the apparent deleted concepts itself.

## Concern-skill partition table (Pass 2)

> **Customise:** map your project's subsystems to concerns.

Match the phase's touched paths to concerns to load:

| Partition touched           | Concerns to load                                    | Domain skills          |
|-----------------------------|-----------------------------------------------------|------------------------|
| `<core-business-logic>/`    | vision, reliability, data, security                 | <your domain skills>   |
| `<api-layer>/`              | security, vision, reliability                       | <your domain skills>   |
| `<auth-layer>/` or admin    | security, vision, operations                        | —                      |
| `<external-integration>/`   | data, security, reliability                         | <integration skill>    |
| `<ui-dir>/`                 | ux, security, vision                                | <ui skills>            |
| `<schema/migration>/` or models | data, operations, reliability                   | —                      |
| Bug fix (any path)          | *above* plus                                        | `systematic-debugging` |

This is the authoritative partition table; keep it in sync with
`review/SKILL.md` §"Concern assignment by partition".

## Output schema (Section 2)

Emit per `.opencode/skills/review/references/finding-schema.md`
with these additions:

- `concerns[]` — list of concerns actually applied (include
  `minimalism` always).
- Finding IDs use: `SEC-`, `VIS-`, `REL-`, `DAT-`, `OPS-`, `MIN-`.
- `cleared[]` — named invariants verified.
- `ambiguity_questions[]` — structured open questions for the
  conductor:

```json
{
  "ambiguity_questions": [
    {
      "id": "Q-01",
      "finding_refs": ["MIN-02", "VIS-04"],
      "question": "minimalism says delete the wrapper; vision says the separation is intentional. Which resolution?",
      "options": [
        "Delete the wrapper and inline its one call site.",
        "Keep the wrapper and document the intent at the call site.",
        "Keep both as tracked follow-ups for a separate refactor."
      ]
    }
  ]
}
```

## Why phase-local deep review is cheap

Catching vision drift, security issues, and bloat at phase
boundary is ~free — the diff is small, the context is fresh, the
implementer is still oriented. Catching the same issues at stage
4 means re-opening a multi-phase plan that might already be
partially merged. Deep review per phase is the cheapest insurance
the workflow buys.
