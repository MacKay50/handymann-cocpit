---
description: Research a system question and write the findings into docs/notes/ (gitignored). Append to an existing note when the slug matches; otherwise create a new one. Depth auto-scales from the subject; honor inline `--quick` / `--deep` overrides.
---

Load the `note` skill (`.opencode/skills/note/SKILL.md`) and run
the research-to-notes workflow on the following subject.

Subject: $ARGUMENTS

Rules of engagement (skill body has the full discipline):

1. Slugify the subject (kebab-case, drop stop words, cap ~60 chars).
2. If `docs/notes/<slug>.md` exists → **append** a dated `## Update`
   section. Do not rewrite existing content.
3. If it doesn't exist → create it with the new-file template.
4. Pick depth: honour `--quick` / `--deep` if present in the
   subject; otherwise auto-classify (factual file-finding →
   quick; cross-plane or "can we / should we" → deep; everything
   else → medium).
5. Read-only outside `docs/notes/`. Never edit source. If you
   find a real bug or refactor opportunity during research, log
   it under the note's "Open questions" section and stop.
6. No subagents. This is a single-agent targeted read. If the
   question genuinely needs RPIR, say so and route the user to
   `develop`.
7. Print a one-line receipt at the end:
   `Wrote docs/notes/<slug>.md (<created|appended>, depth=<level>).`

Begin.
