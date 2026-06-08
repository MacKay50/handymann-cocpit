# Research output schema

Every `researcher` subagent writes a JSON object in this shape to
disk under the slug directory for this research round. The
conductor reads those files when synthesising the brief, and the
resulting plan references the files by path so downstream stages
can resolve any finding ID back to its evidence on demand.

The researcher is *generic* and applies multiple concerns at once.
The top-level field is `concerns` (array) and every finding tags
which concern surfaced it.

## On-disk layout

```
research/
└── <YYYY-MM-DD>-<slug>/                    # one directory per research round
    ├── meta.json                           # conductor writes: slug, date, problem, researcher list
    ├── brief.md                            # conductor writes: synthesised brief (human-facing)
    ├── researcher-1-<concerns>.json        # researcher 1's raw output
    ├── researcher-2-<concerns>.json        # researcher 2 (if spawned)
    ├── researcher-3-<concerns>.json        # researcher 3 (if spawned)
    └── researcher-N-<concerns>-<descriptor>.md   # optional supporting evidence (rare)
```

`<slug>` matches `plans/<YYYY-MM-DD>-<slug>.md` — the plan cites
research anchors by relative path and individual finding IDs.
Anyone reading the plan can `cat` the artifact to see the evidence.

`<concerns>` is the loaded concerns joined by `+` in the order
applied: `code+contract`, `risk`, `options`, `impact+risk`. Keep it
short.

**The directory is gitignored** (`research/` in `.gitignore`).
Artifacts often quote private/internal data; they're regenerable
evidence, not source. The plan committed to `plans/` carries the
anchors; the evidence stays local.

## meta.json — conductor-written index

```json
{
  "slug": "2026-04-19-rate-limit",
  "created": "2026-04-19T14:32:00Z",
  "problem": "Operator asked for a per-customer rate limit.",
  "researchers": [
    { "index": 1, "concerns": ["code", "contract"], "artifact": "researcher-1-code+contract.json" },
    { "index": 2, "concerns": ["risk"], "artifact": "researcher-2-risk.json" }
  ],
  "plan": "plans/2026-04-19-rate-limit.md",
  "status": "synthesised"
}
```

The conductor updates `status` as the round progresses:
`spawning` → `collected` → `synthesised` → `plan-approved` →
`complete`. Lets anyone land in the directory and know where the
round stood.

## Researcher JSON schema

```json
{
  "concerns": ["code", "contract"],
  "problem_summary": "One sentence echo of the problem — confirms you read it right.",
  "findings": [
    {
      "id": "CODE-01",
      "concern": "code",
      "claim": "The rate-limit check is called from exactly two places.",
      "evidence": [
        { "file": "src/api/middleware.py", "line": 87, "snippet": "if rate_limit.check(...):" },
        { "file": "src/admin/sandbox.py", "line": 142, "snippet": "result = rate_limit.check(payload)" }
      ],
      "relevance": "Any change to rate_limit.check's signature needs to update both call sites.",
      "confidence": "high"
    }
  ],
  "decision_points": [
    "Whether the new rate-limit rule lives in middleware.py or a new module.",
    "Whether the runtime-configurable threshold lives in config or a new table."
  ],
  "open_questions": [
    "Is there a requirement to support per-customer overrides? The code has the hook but it's unused."
  ],
  "recommended_anchors": [
    "docs/api.md §Rate limiting",
    "tests/test_middleware.py"
  ],
  "scope_blockers": []
}
```

## Field rules

- `concerns`: array of the concern names this researcher applied
  (e.g. `["code", "contract"]`). Names match the concern-skill
  names with `research-` and `-concerns` stripped.
- `concern` (per finding): which loaded concern surfaced this
  finding. Must be one of the concerns listed in the top-level
  `concerns` array.
- `problem_summary`: one sentence. If you can't summarise the
  problem, the prompt gave you a bad problem statement — raise a
  scope_blocker.
- `findings[]`:
  - `id`: `<CONCERN3-4>-<NN>`, e.g. `CODE-01`, `CONT-02`,
    `IMP-03`, `OPT-A`, `RISK-04`.
  - `claim`: one sentence, factual.
  - `evidence[]`: file:line snippets, doc §references, or command
    output. Must be concrete.
  - `relevance`: one sentence — why does the planner care?
  - `confidence`: `high` / `medium` / `low`.
- `decision_points[]`: concrete choices the plan will have to make.
- `open_questions[]`: things you couldn't resolve from the code
  alone.
- `recommended_anchors[]`: additional docs/tests the planner
  should read.
- `scope_blockers[]`: if populated, the conductor halts synthesis.

## Concern-specific fields

### `options` concern additional fields

```json
{
  "concerns": ["options"],
  "options": [
    {
      "id": "OPT-A",
      "name": "Inline rate-limit rule in existing middleware.py",
      "summary": "Add the new rule as another function in the existing module.",
      "complexity": "low",
      "risk": "low",
      "blast_radius": "middleware.py + test_middleware.py",
      "tradeoffs": "Keeps related code together; grows middleware.py further (currently 320 lines).",
      "vision_alignment": "matches flat structure principle"
    },
    {
      "id": "OPT-B",
      "name": "Extract rate-limit rules to a rules/ subdirectory",
      "...": "..."
    }
  ]
}
```

The `options` concern is the only prescriptive concern — it
proposes approaches. It still doesn't pick one; the planner does.

### `risk` concern additional fields

```json
{
  "concerns": ["risk"],
  "risks": [
    {
      "id": "RISK-01",
      "scenario": "New rate-limit rule added, operator enables it via admin UI, but underlying data doesn't support it (legacy customers without recent activity).",
      "likelihood": "medium",
      "impact": "high",
      "mitigation_hint": "Check field presence in the contract concern and add a precondition.",
      "category": "reliability"
    }
  ]
}
```

`category`: `security` / `reliability` / `vision` / `ops` /
`data` — mirrors the `review` skill's concerns so review can
cross-check.

## How the plan cites these artifacts

The planner writes a `## Research anchors` section at the top of
`plans/<slug>.md` listing every file under `research/<slug>/` with
a one-line summary. Within a phase, the planner cites specific
finding IDs:

```markdown
## Research anchors

- `research/2026-04-19-rate-limit/researcher-1-code+contract.json`
  — call sites of rate_limit.check, schema field availability.
- `research/2026-04-19-rate-limit/researcher-2-risk.json`
  — rollout risks, legacy-customer interaction, operator error modes.
- `research/2026-04-19-rate-limit/brief.md`
  — synthesised brief the user approved.

### Phase 2: add max_per_minute field
...
**Anchors:** CODE-03 (rate_limit.check's 2 call sites), RISK-01
(legacy-customer interaction). Both in researcher-1 and researcher-2
respectively.
```

The implementer and phase-verifier can `cat` any cited file to
verify the plan's premise still holds against the current code.

## Anti-examples

- `claim: "There are some complex parts"` — no location, no
  specific fact. Not a finding.
- `evidence: []` — every finding needs evidence.
- Solutions in research output — only the `options` concern
  proposes approaches. Other concerns describe.
- Missing `decision_points[]` on a substantial research output —
  research without decision points gives the planner nothing to
  plan around.
- Writing anywhere outside `research/<slug>/`. The permission
  system blocks it; the finding would be rejected.
- Inventing a slug. The conductor provides the slug; researchers
  never pick their own.
