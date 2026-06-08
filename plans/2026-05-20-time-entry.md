# Plan: Employee + TimeEntry
**Slug:** 2026-05-20-time-entry
**Date:** 2026-05-20
**Classification:** Standard (to nye ressourcer, FK-kæde, beregning, CPR-masking)

## Vision-invarianter
- §1 Kunden er omdrejningspunktet: time_entry → project_id → customer. ✓
- §2 LLM anbefaler, kode beslutter: `total` beregnes altid server-side. ✓
- §3 Fejl er synlige: ingen 0-defaults på finansielle felter; FK-fejl → 422. ✓
- §4 Revisionsspor: soft-delete på begge tabeller. ✓
- §6 Følsomme data maskeres: `cpr_number` returneres aldrig klartekst. ✓

## Out of scope
- Lønseddel-beregning, overarbejdstillæg
- Employee → auth/login
- Kobling til tilbud/faktura
- Expense/transport (RPIR 2)

## Rollback
Slet `models/employee.py`, `models/time_entry.py`, `api/employees.py`, `api/time_entries.py`, `tests/test_employees.py`, `tests/test_time_entries.py`. Revert `main.py` og `models/__init__.py`.

---

## Fase 1 — Employee CRUD

### Acceptance criteria
1. `POST /employees/` → 201, `EmployeeRead` med `cpr_masked` (ikke `cpr_number`)
2. `POST /employees/` med `cpr_number` sat → `cpr_masked = "****{last4}"`
3. `GET /employees/` → liste af aktive medarbejdere
4. `GET /employees/{id}` → 200 eller 404
5. `PATCH /employees/{id}` → 200, opdaterede felter
6. `DELETE /employees/{id}` → 204, soft-delete
7. `python -m pytest tests/test_employees.py -v` → alle grønne
8. `python -m ruff check src/ tests/` → ingen findings

### Filer
| Fil | Handling |
|-----|----------|
| `src/haandvaerker/models/employee.py` | Ny |
| `src/haandvaerker/api/employees.py` | Ny |
| `tests/test_employees.py` | Ny |
| `src/haandvaerker/models/__init__.py` | Opdater |
| `src/haandvaerker/main.py` | Opdater |

---

## Fase 2 — TimeEntry CRUD + summary

### Acceptance criteria
9. `POST /time-entries/` med gyldig project_id + employee_id → 201
10. `POST /time-entries/` uden hourly_rate → bruger Employee.default_hourly_rate
11. `POST /time-entries/` med hourly_rate override → bruger override-værdien
12. `total` beregnet korrekt: `hours × hourly_rate` (Decimal præcision)
13. `POST /time-entries/` med ukendt project_id → 422
14. `POST /time-entries/` med inaktivt project → 422
15. `POST /time-entries/` med ukendt employee_id → 422
16. `POST /time-entries/` med inaktiv employee → 422
17. `GET /time-entries/` → liste
18. `GET /time-entries/?project_id=X` → filtreret
19. `GET /time-entries/?employee_id=X` → filtreret
20. `GET /time-entries/summary?project_id=X` → total_hours, total_cost, billable_hours, billable_cost
21. `GET /time-entries/{id}` → 200 eller 404
22. `PATCH /time-entries/{id}` → opdateret entry med genberegnet total
23. `DELETE /time-entries/{id}` → 204, soft-delete
24. `python -m pytest tests/ -v` → alle grønne (inkl. regression)
25. `python -m ruff check src/ tests/` → ingen findings

### Filer
| Fil | Handling |
|-----|----------|
| `src/haandvaerker/models/time_entry.py` | Ny |
| `src/haandvaerker/api/time_entries.py` | Ny |
| `tests/test_time_entries.py` | Ny |
| `src/haandvaerker/models/__init__.py` | Opdater |
| `src/haandvaerker/main.py` | Opdater |

### TDD-rækkefølge (begge faser)
1. Skriv test_employees.py → fejler
2. Implementer employee model + API → grøn
3. Skriv test_time_entries.py → fejler
4. Implementer time_entry model + API → grøn
5. Ruff → ren

### Follow-ups
- FU-9: Overarbejdstillæg (timepris × faktor efter 37 timer/uge)
- FU-10: Direkte kobling TimeEntry → QuoteLine (fakturering fra timer)
- FU-11: Ugeseddel-view (sum pr. medarbejder pr. uge)
