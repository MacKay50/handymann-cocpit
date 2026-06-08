# Plan: Projekter-ressource
**Slug:** 2026-05-19-projekter-ressource
**Date:** 2026-05-19
**Classification:** Standard (ny public API-surface, FK-validering, enum)

## Vision-invarianter checket
- §1 Kunden er omdrejningspunktet: `customer_id` er påkrævet FK ✓
- §3 Fejl er synlige: ingen stille defaults, 422 ved manglende/ukendt customer_id ✓
- §5 Flad struktur: én model-fil, én router-fil, registreret ét sted ✓
- §7 Design for nem ændring: policy (status-transitions) adskilt ✓

## Out of scope
- Alembic-migration (separat)
- `end_date < start_date` validering
- Kaskade-soft-delete til sub-ressourcer
- Relations til TimeEntry, Quote, Expense

## Rollback
- Fase 1 er ren ny kode (ingen ændringer til eksisterende filer undtagen `main.py` og `models/__init__.py`)
- Rollback: slet `src/haandvaerker/models/project.py`, `src/haandvaerker/api/projects.py`, `tests/test_projects.py`; revert de to linjer i `main.py` og `models/__init__.py`

---

## Fase 1 — Project model + CRUD + tests

### Acceptance criteria (alle verificerbare)
1. `POST /projects/` med gyldig `customer_id` → 201 + `ProjectRead`
2. `POST /projects/` med ukendt `customer_id` → 422
3. `POST /projects/` med inaktiv `customer_id` → 422
4. `POST /projects/` uden `customer_id` → 422 (Pydantic-validering)
5. `GET /projects/` → liste af aktive projekter
6. `GET /projects/?customer_id=<id>` → filtreret liste
7. `GET /projects/?status=active` → filtreret liste
8. `GET /projects/<id>` → `ProjectRead` eller 404
9. `PATCH /projects/<id>` med delvise data → opdateret `ProjectRead`
10. `DELETE /projects/<id>` → 204, projekt `active=False`, stadig tilgængeligt via GET
11. `POST /projects/` med eksisterende `id` → 409
12. `python -m pytest tests/ -v` — alle tests grønne
13. `python -m ruff check src/ tests/` — ingen findings

### Filer der berøres
| Fil | Handling |
|-----|----------|
| `src/haandvaerker/models/project.py` | Ny |
| `src/haandvaerker/api/projects.py` | Ny |
| `tests/test_projects.py` | Ny |
| `src/haandvaerker/models/__init__.py` | Opdater: tilføj Project-exports |
| `src/haandvaerker/main.py` | Opdater: registrer projects_router |

### TDD-rækkefølge
1. Skriv `tests/test_projects.py` med alle 11 test-cases → alle fejler (ImportError/404)
2. Implementer `models/project.py`
3. Implementer `api/projects.py`
4. Registrer i `main.py` og `models/__init__.py`
5. Kør tests → alle grønne
6. Kør ruff → ren

### Follow-ups (logges, implementeres ikke nu)
- FU-1: `end_date < start_date` validering i `ProjectCreate`
- FU-2: Alembic-migration for `project`-tabel
- FU-3: Kaskade-soft-delete: deaktivering af Customer → advarsel hvis aktive Projects
