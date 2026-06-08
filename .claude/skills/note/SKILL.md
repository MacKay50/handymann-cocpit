---
name: note
description: Use when the user types `/note "<subject>"`, runs the `/note` slash command, or says "make a note about X", "add to notes: ...", "research X and write it down", "/note --deep ...". Targeted single-agent research-to-notes workflow. Reads the codebase to answer one question and writes the findings to `docs/notes/<slug>.md` (gitignored). Append to existing notes when the slug already exists; one organic note per topic, dated `## Update` sections. Read-only outside `docs/notes/`. Not a substitute for `develop` (RPIR) or `review` — this is the "let me check and write it down" pass.
license: MIT
compatibility: opencode
metadata:
  audience: any agent
  workflow: research-to-notes
---

# note — targeted research, append to docs/notes/

You are answering one question and writing the answer down. The
question is the user's literal subject string. The output is one
markdown file under `docs/notes/` and nothing else.

This is **not** RPIR. There's no plan, no implementation, no
verification, no subagents. It's the read-only "let me check"
pass that produces a durable note future-you can re-read instead
of re-investigating.

## When to load

- Slash command: `/note "<subject>"` (via `.opencode/command/note.md`)
- "Note this:", "make a note about X", "add to notes: ..."
- "Research X and write it down for later"
- "Can we [...] ?" / "Should we [...] ?" — when the user wants a
  written answer they can re-read, not just an inline reply
- "Investigate X but don't change anything yet"

If the user wants the answer **in chat with no file write**, this
isn't the skill — just answer them. If they want a plan or code
change, route to `develop`. If they want a reshape audit of a
subsystem, route to a `refactor-audit` skill (not shipped in this
starter — see `HARNESS.md` §11).

## Three depths

Pick one. Default is **medium**. Users can override with
`--quick` / `--deep` anywhere in the subject string.

| Depth | Trigger | Time budget | Tools |
|---|---|---|---|
| **quick** | `--quick` flag, or factual one-liner ("where does X live?", "what does Y mean?") | < 2 min | Glob, Grep, Read on at most 3 files |
| **medium** (default) | Anything not obviously quick or deep | 5-10 min | Above + targeted file reads, `AGENTS.md` / `vision.md` cross-check |
| **deep** | `--deep` flag, or question spans 2+ subsystems, or "can we / should we" architectural questions | 15-30 min | Above + multi-pass Glob/Grep + cross-plane + risk pass |

### Auto-classification rules

Apply in order; first match wins:

1. Subject contains `--quick` or `--deep` → use that depth.
2. Subject is a factual lookup ("where", "what", "which file",
   "list ...") → quick.
3. Subject crosses subsystems (mentions ≥ 2 top-level
   directories) OR uses architectural framing ("can we", "should
   we", "is X feasible") → deep.
4. Otherwise → medium.

If unsure between two depths, pick the lower one and offer to go
deeper at the end.

## Slug + filename

Slugify the subject:

- kebab-case
- drop stop words (the, a, of, in, on, by, to, for, is, are)
- cap at ~60 chars
- lowercase

Examples:
- "Where does the API throttle live?" → `api-throttle-location`
- "Can we move the auth check to the gateway?" → `move-auth-check-to-gateway`

Filename: `docs/notes/<slug>.md`

## Append vs create

- **If `docs/notes/<slug>.md` exists** → **append** a dated
  `## Update <YYYY-MM-DD>` section. Do not rewrite existing
  content. Existing notes are durable; updates layer on top.
- **If it doesn't exist** → create it with the new-file template
  below.

This rule is load-bearing. Each note is one organic document for
its topic, growing over time. Don't fragment.

## New-file template

```markdown
# <Subject as-typed by user>

**Created:** <YYYY-MM-DD>
**Depth:** quick | medium | deep

## TL;DR

<2-4 sentences. The actual answer.>

## What I found

<Body. Cite `file:line` for code claims, doc§ for prose claims.
Bullet points or short prose; no padding.>

## Open questions

<Anything you couldn't resolve. The next /note --deep run picks
these up. Empty bullet list is fine; "(none)" is the explicit form.>

## Receipt

Read X files, scanned Y paths, Z minutes elapsed.
```

## Append template

```markdown
## Update <YYYY-MM-DD>

**Trigger:** <what prompted this update — usually a quote of the
new subject string>
**Depth:** quick | medium | deep

<Body. Same rules as the original. Cite. Don't restate the
original — say what's new or different.>

### Open questions (delta)

<Add to the original list, or note which open questions are now
resolved.>
```

## Hard rules

- **Read-only outside `docs/notes/`.** Never edit source. If you
  find a real bug or refactor opportunity during research, log it
  under "Open questions" and stop.
- **No subagents.** This is single-agent. If the question really
  needs RPIR, say so and route to `develop`.
- **Cite or drop.** No "I think X" — either you can cite it or you
  raise it as an open question.
- **Don't pad.** A medium note is 30-100 lines, not 300.
- **Print a one-line receipt at the end** of your chat reply:

  ```
  Wrote docs/notes/<slug>.md (<created|appended>, depth=<level>).
  ```

## When the answer is "we don't know yet"

Write the note anyway. The Open questions section is the *value*
of the note when the question is unresolvable from the code alone.
A note that says "I traced X to Y but couldn't determine Z without
running it" is more useful than no note.
