# Plan: Tilbud-ressource (Quote)
**Slug:** 2026-05-20-tilbud-ressource
**Date:** 2026-05-20
**Classification:** Complex (ny public API-surface, beregningslogik, statusmaskine, nested creates)

## Vision-invarianter checket
- §1 Kunden er omdrejningspunktet: quote → project_id (FK) → customer. Ingen quote uden projekt. ✓
- §2 LLM anbefaler, kode beslutter: moms og totaler beregnes altid af kode. ✓
- §3 Fejl er synlige: ingen stille defaults på beløb/moms. Mangler → 422. Ugyldig overgang → 409. ✓
- §4 Revisionsspor: quote er soft-delete. Statusovergange er enkelt-vejede (ingen direkte PATCH på status). ✓
- §5 Flad struktur: én model-fil, én router-fil, registreret ét sted. ✓

## Out of scope
- PDF-generering, email-afsendelse
- Tilbudsversioner / revisioner
- Materialeberegner (maling-liter fra m2)
- Automatisk expired-status
- Decimal/Numeric end-to-end (FU-5)

## Rollback
- Ny kode kun. Rollback: slet quote.py, quotes.py, test_quotes.py; revert 2 linjer i main.py og models/__init__.py.

---

## Fase 1 — Tilbud: modeller, CRUD, opmåling, statusmaskine

### Acceptance criteria
1. `POST /quotes/` med gyldig `project_id`, title → 201, `QuoteRead` med `quote_number` = `TIL-{år}-001`
2. `POST /quotes/` med `rooms` → `QuoteRoomRead` i svaret med beregnede `wall_m2`, `ceiling_m2`, `floor_m2`, `wall_m2_net`
3. `POST /quotes/` med `lines` → `subtotal`, `vat_amount`, `total` beregnet korrekt (moms = 25%)
4. `POST /quotes/` med ukendt `project_id` → 422
5. `POST /quotes/` uden `project_id` → 422
6. `GET /quotes/` → liste af aktive tilbud
7. `GET /quotes/?project_id=<id>` → filtreret liste
8. `GET /quotes/?status=draft` → filtreret liste
9. `GET /quotes/<id>` → `QuoteRead` med rooms og lines, eller 404
10. `PATCH /quotes/<id>` på draft → 200, opdateret titel/felter
11. `PATCH /quotes/<id>` på non-draft → 409
12. `PATCH /quotes/<id>` med nye lines → totaler genberegnet
13. `POST /quotes/<id>/send` på draft → 200, status = sent
14. `POST /quotes/<id>/accept` på sent → 200, status = accepted
15. `POST /quotes/<id>/reject` på sent → 200, status = rejected
16. `POST /quotes/<id>/accept` på draft → 409 (ugyldig overgang)
17. `DELETE /quotes/<id>` → 204, soft-delete, stadig tilgængeligt direkte
18. Andet quote på samme projekt → `quote_number` = `TIL-{år}-002`
19. `wall_m2_net` er aldrig negativ (self-fradrag kan ikke give negativt)
20. `python -m pytest tests/ -v` — alle tests grønne
21. `python -m ruff check src/ tests/` — ingen findings

### Filer der berøres
| Fil | Handling |
|-----|----------|
| `src/haandvaerker/models/quote.py` | Ny — 4 modeller + beregningsfunktioner |
| `src/haandvaerker/api/quotes.py` | Ny — router + 8 endpoints |
| `tests/test_quotes.py` | Ny — 22 test-cases |
| `src/haandvaerker/models/__init__.py` | Opdater: Quote-exports |
| `src/haandvaerker/main.py` | Opdater: quotes_router |

### TDD-rækkefølge
1. Skriv `tests/test_quotes.py` → alle fejler (ImportError/404)
2. Implementer `models/quote.py`
3. Implementer `api/quotes.py`
4. Registrer i `main.py` og `models/__init__.py`
5. Kør tests → alle grønne
6. Kør ruff → ren

### Follow-ups
- FU-4: `active`-felt i `CustomerUpdate` (pre-existing, fix inden Customer bruges i livscyklus-guards)
- FU-5: Brug `Numeric(10,2)` + Python `Decimal` end-to-end i stedet for float
- FU-6: Tilbudsversioner — ny revision af sendt tilbud
- FU-7: Automatisk `expired`-overgang baseret på `valid_until`-dato
- FU-8: Materialeberegner — beregn antal liter maling fra m2 (baseret på dækningsevne)
