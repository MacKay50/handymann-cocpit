# CLAUDE.md — Claude Code entry point

> **You are Claude Code reading this on session start.** This file
> is the meta-context for the agent harness this repo defines.
> Read it once per session, then defer to the project's
> `vision.md` and `AGENTS.md` for product/architectural context.

---

## What this repo is

An **agent harness starter** — a distilled, opencode-and-Claude-Code
compatible scaffold for running non-trivial code changes through a
disciplined Research → Plan → Implement → Review (RPIR) workflow.

The harness was originally written for opencode and ported to
Claude Code. **Both runtimes are first-class** — the canonical
files live in `.opencode/` and `.claude/` as parallel trees that
share the same skill content (Anthropic Agent Skills and opencode
skills use identical `SKILL.md` frontmatter, so the `skills/`
subtree is shared verbatim).

**You are operating in the Claude Code variant.** When you Tab to
an agent or call a subagent, the file the system finds is
`.claude/agents/<name>.md`. When you load a skill, it's
`.claude/skills/<name>/SKILL.md`. When the user types a slash
command, it's `.claude/commands/<name>.md`.

---

## What to read first

In this priority order. The first three are mandatory; the rest
are reference.

1. **`vision.md`** — the product north star. Design principles
   the plan-verifier checks against. Read in full.
2. **`AGENTS.md`** — the technical kickstart. Repo layout, build
   commands, key design rules, simple-change workflow rubric.
   Read in full.
3. **This file (`CLAUDE.md`)** — the harness wrapper. Already
   here.
4. **`HARNESS.md`** — architecture and *why*. Read when you need
   to understand or change the harness itself.
5. **`CHEATSHEET.md`** — one-page mental model. Reference.
6. **`ADOPTION.md`** — how a new project adopts the harness. Read
   when applying to a new project.
7. **`PORTING-TO-CLAUDE-CODE.md`** — opencode↔Claude Code
   conversion reference. Read when changing how Claude Code reads
   the harness.

> **Important:** `vision.md` and `AGENTS.md` are templates in this
> starter. A fresh clone has placeholder content. The user's job
> is to fill them in for their project. If they're still
> placeholder, point that out — the harness can't grade plans
> against `<PLACEHOLDER>` invariants.

---

## The harness in one paragraph

Two primary agents the user invokes (`develop-conductor` for
RPIR, `review-conductor` for read-only audits) orchestrate six
subagents (`researcher`, `planner`, `plan-verifier`,
`implementer`, `phase-verifier`, `reviewer`) with strict role
separation. The conductor never writes source. The implementer
never commits. Verifiers never write at all. Research evidence
lives at `research/<slug>/*.json` (gitignored, regenerable). Plans
live at `plans/<slug>.md` (committed, the contract). Every stage
ends at the user — never silently resolve ambiguity.

The seven phase-verifier gates (secrets, lint ratchet, cleanup
completeness, net LoC + minimalism warning, frontend lint,
acceptance criteria, scope drift) gate auto-commit. Auto-commit
fires only on Section-3 clean PASS — never on `PASS WITH
FOLLOWUP` or `FAIL`.

Three Iron Laws cited from `vision.md` and `AGENTS.md`:
1. **Ask the user on ambiguity.** Frame options. Never silently
   pick a side.
2. **Fail loud, never mask.** A visible error beats a silent
   wrong number. Masking fallbacks (silent defaults on failed I/O)
   are high-severity bugs by definition.
3. **LLM recommends, code decides.** Every consequential decision
   is deterministic code. The LLM classifies, parses, drafts text.

---

## When the user types `Tab` or asks for work

| User intent                                       | Route to                              |
|---------------------------------------------------|---------------------------------------|
| "plan X", "implement Y", "build feature", "ticket"| `develop-conductor` subagent          |
| "review", "audit", "pre-PR check", "security review" | `review-conductor` subagent       |
| Trivial fix (typo, comment, single-line, no high-stakes path) | yourself, in the main session, following the simple-change rubric in `AGENTS.md` |
| "/note <subject>"                                 | the `note` skill via the slash command |
| "let me just check X"                             | yourself, then suggest `/note` to write it down |

Subagents are invoked via the `Task` tool with the matching
`subagent_type`. Example:

```
Task(subagent_type="develop-conductor",
     description="Plan refund-cap feature",
     prompt="<the user's actual request>")
```

The agent definition at `.claude/agents/develop-conductor.md`
will load, with its system prompt, tools, and any frontmatter-
declared model.

---

## Simple-change workflow (you, in the main session)

For trivial changes you handle directly without spawning the
conductor. The full rubric lives in the user's `AGENTS.md`
§"Simple-change workflow", but the spine is:

**Trivial = ALL of these true:**
- Net diff under ~50 lines.
- One file or a small handful of tightly-scoped files in the
  same subsystem.
- **Does NOT touch any high-stakes path** (per AGENTS.md
  exclusions list).
- Not introducing a new public surface, config key, or migration.
- Not a behaviour change exposed externally.

**When you're handling a trivial change directly, you still:**
1. **Read `vision.md` first** (short).
2. **Read `AGENTS.md`** for repo layout + design rules.
3. **Follow code-minimalism by default** — load
   `.claude/skills/code-minimalism/SKILL.md` if uncertain.
4. **Write a failing test first** if the change has observable
   behaviour. Skip only for pure docs / pure config / comment-
   only edits.
5. **Run the relevant local check** before handing back —
   whatever the user's `AGENTS.md` §"How to test" lists.
6. **Respect the lint ratchet** — no new findings on net-new
   lines.
7. **Do not commit unprompted.** The user decides commits.
8. **Escalate to `develop-conductor` the moment the change grows
   past the simple threshold** — mid-task, if you discover the
   fix really does touch a high-stakes path or needs >50 lines,
   stop and say so.

---

## The Iron Laws — load-bearing prose

These three rules apply to **every agent in the harness**,
including you in the main session. They're cited (not restated)
in skill bodies, agent definitions, and verifier rubrics.

### Iron Law 1 — Ask the user on ambiguity

> NEVER resolve ambiguity silently. Frame options. Ask.

Rationalisations to reject:

| If you're thinking… | Reality |
|---|---|
| "the answer is obviously X" | If it were obvious, the prompt wouldn't have been ambiguous. Ask. |
| "asking will annoy the user" | Guessing wrong annoys them more. Ask. |
| "the options are equivalent" | Then say so and ask which they prefer. Equivalence is itself a choice. |
| "it's a small detail, the user doesn't care" | Let them decide that. Ask. |
| "the user is busy" | They delegated implementation, not decisions. Ask. |

### Iron Law 2 — Fail loud, never mask

> A visible error is always preferable to a silent wrong number.

**Legitimate fallback (allowed):** startup/config fallback to a
known-good default when a dependency is unavailable at boot.
Narrow, bounded, logged at WARN, tested.

**Masking fallback (forbidden):** runtime substitution of a
plausible-looking value for a failed call, missing field, or
unexpected exception. Examples:

```python
amount = parsed.get("amount", 0)            # 0 looks valid; isn't
result = client.fetch() or DEFAULT          # silently substitutes
try:
    value = external_api()
except Exception:
    value = None                            # broad except + silent default
```

All forbidden. The fix is always: **fail loud, escalate, log
with context, increment a counter**. Full discipline:
`.claude/skills/code-minimalism/SKILL.md` §3.

### Iron Law 3 — LLM recommends, code decides

> Every consequential decision is deterministic code. The LLM
> classifies, parses, and drafts text.

Applies to the harness itself: gate verdicts are computed from
the diff, not asked of the LLM. Commit decisions are made by
checking pass-conditions in prose, not by asking the LLM "should
I commit?".

---

## Tool conventions (Claude Code)

The agents in `.claude/agents/` use these tools (frontmatter
`tools:` field). Tool names are case-sensitive:

- `Read`, `Write`, `Edit` — file operations
- `Bash` — shell commands
- `Glob`, `Grep` — search
- `Task` — spawn a subagent
- `WebFetch`, `WebSearch` — external content (most agents have
  these denied)
- `TodoWrite` — task tracking (only conductors typically use it)

**Project-wide permissions** are in `.claude/settings.json`. They
control what `Bash(<pattern>)` invocations are allowed. The
starter ships sensible defaults; users tighten or loosen per
their project.

**Per-agent role separation** in Claude Code relies on:
1. The agent's `tools:` list (e.g., reviewers don't have `Edit`).
2. The agent's prompt body declaring what it does and doesn't do
   (e.g., "I am the implementer and I do not commit").
3. Optional hooks in `.claude/settings.json` (e.g., a `PreToolUse`
   hook on `Bash` that blocks `git commit` from non-conductor
   agents). Not enabled by default; see
   `PORTING-TO-CLAUDE-CODE.md` §"Hardening role separation with
   hooks".

This is **slightly less granular than opencode**, where each
agent's frontmatter declares its own bash allowlist. The
trade-off and how to harden it are documented in
`PORTING-TO-CLAUDE-CODE.md`.

---

## On-disk artifact contract (unchanged from opencode)

| Path                                        | Tracked? | Written by              |
|---------------------------------------------|----------|-------------------------|
| `research/<slug>/meta.json`                 | no       | develop-conductor       |
| `research/<slug>/researcher-N-<concerns>.json` | no    | researcher (index N)    |
| `research/<slug>/brief.md`                  | no       | develop-conductor       |
| `plans/<slug>.md`                           | yes      | planner                 |
| `docs/notes/<slug>.md`                      | no       | note skill              |

`<slug>` = `<YYYY-MM-DD>-<kebab-description>`. Same slug ties
`research/<slug>/` and `plans/<slug>.md` together. The
gitignored directories (`research/`, `docs/notes/`) are listed in
the project `.gitignore`.

---

## When something seems off

- **A skill body says "the gate silently didn't run if you didn't
  load this skill".** Take it literally. Load the skill.
- **`vision.md` is `<PLACEHOLDER>`.** Tell the user before
  proceeding — the plan-verifier has nothing to check against.
- **The user asks you to commit but the phase-verifier returned
  `PASS WITH FOLLOWUP`.** Confirm explicitly — auto-commit fires
  only on clean PASS. PASS WITH FOLLOWUP is a user decision.
- **The user asks you to bypass a gate ("just commit anyway").**
  Surface the trade-off. The gate exists for a reason cited in
  `HARNESS.md` §12. If they still want it bypassed, do so with
  acknowledged override, never silently.
- **You can't decide between two interpretations of the user's
  request.** Iron Law 1. Frame options, ask.

---

## How this file relates to AGENTS.md

`AGENTS.md` is the **canonical project context** — it's read by
opencode, by Claude Code (via this file's pointer), by a fresh
new hire reading the repo, and by anyone running an agent
runtime. The user fills it in once.

`CLAUDE.md` (this file) is the **Claude-Code-specific entry
point** — it has the same role for Claude Code that opencode's
top-level config has for opencode. It points at AGENTS.md so the
project context stays single-source.

When updating: edit `AGENTS.md` for project facts (build
commands, design rules, repo layout). Edit this file only when
something about Claude Code's runtime semantics changes.

---

## Further reading

- `HARNESS.md` — architecture and the *why* behind every rule
- `CHEATSHEET.md` — one-page mental model
- `ADOPTION.md` — how to apply this to a new project
- `PORTING-TO-CLAUDE-CODE.md` — opencode↔Claude Code conversion
  reference and the rationale for the differences
- `.claude/skills/develop/SKILL.md` — the RPIR playbook itself
- `.claude/skills/code-minimalism/SKILL.md` — the cross-cutting
  discipline
- `.claude/agents/references/phase-verifier-rubric.md` —
  authoritative gate spec
