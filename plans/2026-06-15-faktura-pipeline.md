# Plan: Faktura-pipeline -- luk "samles op" og "aldrig restance"

**Path:** plans/2026-06-15-faktura-pipeline.md
**Created:** 2026-06-15
**Research:** research/2026-06-15-faktura-pipeline/
**Status:** GODKENDT af Anton (2026-06-15) -- klar til implementering

## Research anchors

Artefakter (gitignored -- regenereres med develop-conductor hvis de mangler):

- research/2026-06-15-faktura-pipeline/brief.md -- synthesiseret brief.
- researcher-1-code-contract.json -- eksisterende faktura-infrastruktur: to verdener
  (CODE-01), komplet analyse-pipeline (CODE-02), API+UI (CODE-03), dev-only ingestion
  (CODE-04), manglende email-routing (CODE-05), ubrugt betalingsbro (CODE-06),
  reconciliation matcher kun penge ind (CODE-07), status-maskine (CONTRACT-01),
  migrationskonvention (CONTRACT-02), CompanyContextDep (CONTRACT-03), regex-stubs (CONTRACT-04).
- researcher-2-impact-risk-options.json -- huller (IMPACT-01..03), risici (RISK-01..05),
  faseforslag (OPT-A..D).

Faser nedenfor citerer finding-ID-er hvor en beslutning er forankret i evidens.

## Loeste spoergsmaal (godkendt af Anton 2026-06-15)

Alle fire aabne spoergsmaal er besvaret af Anton og laast. Planens forslag stod ved magt
paa alle fire -- ingen aendring af fasestruktur eller acceptance criteria var noedvendig,
kun bekraeftelse. (Den fulde spoergsmaalsformulering staar uaendret nederst under
"Open questions for the user", nu historik.)

1. **Ingestion-kilde (RISK-05) -> (a).** Faktura-emails kommer ind paa fx
   `faktura@malerfirmaet-pll.dk`. Vi genbruger **InboxMessage direkte** som kilde til
   InvoiceCase -- ingen separat MailMessage-post, mindst kode. Forfremmelsen er idempotent
   paa inbox-message-id (Fase 1).
2. **Fase-omfang -> alle 4 faser.** Vi koerer Fase 1-3 (kerne) plus Fase 4
   (needs_review-haerdning). Fase 4 er ikke laengere "valgfri" -- den er en del af leverancen.
3. **Overdue-mekanisme (OPT-B, Fase 2) -> endpoint nu, baggrundsjob senere.** Genberegning
   sker ved visning via et endpoint (`POST /invoice-monitoring/recompute-priorities`).
   Et periodisk baggrundsjob er en separat fremtidig opgave (out of scope her).
4. **Auto-confirm-praecision (Fase 3) -> eksakt beloeb + betalingsreference + dato inden for
   7 dage.** Kun naar alle tre matcher saetter systemet selv status `payment_confirmed`. Alt
   andet kraever manuel bekraeftelse (Iron Law 3, spejler kunde-siden CODE-07).

## Problem

INDGAAENDE kreditor-fakturaer (leverandoer -> haandvaerker) skal samles op, analyseres,
haandteres og aldrig ende i restance. Den levende kode har allerede Betalingsradar:
datamodel, 12-trins analyse-pipeline, 10 API-endpoints og fuldt UI (CODE-01..03). To
huller staar tilbage mod Antons maal: (1) "samles op" har ingen produktionsvej -- eneste
indgang er en dev-knap der returnerer 403 i prod, saa faktura-emails fanges som inbox-items
men forfremmes aldrig til InvoiceCase (CODE-04, CODE-05, IMPACT-01); (2) "aldrig restance"
har ingen lukke-loop -- prioritet genberegnes ikke over tid (IMPACT-03) og
betalingsbekraeftelse er en ubrugt stub (CODE-06, IMPACT-02).

## Approach

Vi BYGGER ikke radaren om -- vi lukker de to huller ved at genbruge eksisterende
infrastruktur (OPT-A, OPT-B, OPT-C). Tre kernefaser: (1) wire produktions-ingestion fra
email til betalingsradar; (2) proaktiv daglig overdue-eskalering der genberegner prioritet;
(3) wire den eksisterende betalingsbro til en debet-bankmatcher saa loopet lukkes. En
fjerde lille fase (OPT-D) haerder risikable ekstraktioner (amount=0 / manglende forfald ->
needs_review). Hver fase er additiv-minimal og genbruger compute_priority, monitoring-
pipelinen og reconciliation_bridge der allerede findes.

## Architectural posture

Incumbent pattern: vi UDVIDER, ikke redesigner. Betalingsradaren
(services/invoice_monitoring/*) er et veldefineret subsystem med en ren intern pipeline og
en reconciliation-bro-kontrakt (CODE-02, CODE-06). Alle fire faser haenger paa eksisterende
udvidelsespunkter:

- Separation of concerns: ingestion-routing hoerer i inbox_ingest (transport/routing-laget),
  ikke i monitoring-servicen. Vi refaktorerer monitoring_service.ingest_sample saa
  forretningslogikken kan kaldes fra baade dev-knappen og email-pathen -- policy adskilt fra
  transport (vision afsnit 7). Betalingsmatch hoerer i reconciliation-laget der kalder broen.
- Pick-up-ability: en ny udvikler finder ingestion-routing samme sted som den eksisterende
  new_quote_request-routing, og betalingsmatch samme sted som kunde-side-matcheren.
- Extensibility: efter planen er naeste relaterede aendring lettere fordi loopet er lukket og
  audit-eventtyperne (priority_raised, sent_to_reconciliation, payment_confirmed) emitteres.
- Security/stability: ingen ny trust-graense. Fase 3 udvider reconciliation til
  debet-transaktioner; mitigering: auto-confirm KUN paa eksakt beloeb+reference-match
  (Iron Law 3), ellers human-confirm -- spejler eksisterende kunde-side-praksis (CODE-07).

Debt: ingestion-broen InboxMessage->InvoiceCase introducerer en kobling mellem to
inbox-modeller (RISK-05). Betales ned ved at goere InvoiceCase-kilden entydig
(idempotensnoegle), ikke ved at duplikere lagring.

## Invariants preserved

- vision afsnit 2 / Iron Law 3 -- LLM anbefaler, kode beslutter: al prioritet og alle
  betalingsmatch er deterministisk kode; auto-confirm kun ved eksakt match.
- vision afsnit 3 / Iron Law 2 -- fejl synlige: fase 4 sikrer at amount=0 / manglende
  forfald giver needs_review-eskalering, ikke en stille gul sag (RISK-01/02).
- vision afsnit 4 -- revisionsspor: alle tilstandsskift emitter InvoiceEvent (append-only).
- CONTRACT-02 / RISK-03 -- demo-data bevares: kun additive manuelle SQL-migrationer. Nye
  tabeller via create_all(); nye kolonner via ALTER-script. ALDRIG reset_demo.bat.
  PLL / Gentofte BygningsService / CSKK bevares.
- CONTRACT-03 -- multi-tenant: alle nye queries filtrerer paa company_id via CompanyContextDep.

## Phases

### Phase 1: Produktions-ingestion fra email til betalingsradar

**Goal.** Faktura-emails (invoice_payment) forfremmes automatisk til InvoiceCase i
produktion, idempotent, via den eksisterende monitoring-pipeline.

**Anchors.** CODE-04, CODE-05, OPT-A, IMPACT-01, RISK-04, RISK-05, CONTRACT-03.

**Files.**
```
src/haandvaerker/services/invoice_monitoring/monitoring_service.py
src/haandvaerker/services/inbox_ingest.py
src/haandvaerker/models/invoice_case.py
migrations/2026-06-15-invoice-case-source-inbox.sql
tests/test_invoice_ingestion_routing.py
```

**Dependencies.** None.

**Acceptance criteria.**
1. pytest tests/test_invoice_ingestion_routing.py passerer, inkl.: (a) en InboxMessage
   klassificeret invoice_payment skaber praecis een InvoiceCase + InvoiceActionItem; (b)
   gentagen ingest af samme InboxMessage skaber IKKE en ny case (idempotens, RISK-04);
   (c) en new_quote_request-besked skaber IKKE en InvoiceCase (ingen regression).
2. monitoring_service eksponerer en intern ingest_from_inbox(session, inbox_message, ...)
   som baade dev-knappen og inbox_ingest kalder (ingen duplikeret pipeline-kode).
3. Soegning paa ingest_sample i src/ viser kun dev-endpoint + intern delegering (ikke ny logik).
4. InvoiceCase har en entydig source-noegle paa inbox-message-id; migration tilfoejer kolonnen
   additivt uden at roere eksisterende rows.

**Deletions.**
- Duplikeret felt-flettelogik i ingest_sample flyttes til ingest_from_inbox (ingest_sample
  bliver en tynd wrapper -- netto fjernes gentaget kode).

**Subtraction check.** Kan opnaas rent ved sletning? Nej -- routing er ny adfaerd. Men
pipeline-koden centraliseres (een kilde) frem for at kopieres, saa netto-tilvaeksten holdes lav.

**Rollback.** Revert commit. Migrationen er additiv (nullable kolonne) -- ingen data-tab ved
revert; kolonnen kan staa ubrugt.

**Net LoC intent.** ca. +80 / -25.

### Phase 2: Proaktiv overdue-eskalering

**Goal.** Et dagligt job/endpoint genberegner prioritet for aabne cases ud fra dagens dato og
loefter mod red naar forfald naermer sig/passeres, saa ingen faktura glider uset.

**Anchors.** IMPACT-02, IMPACT-03, OPT-B, CONTRACT-01.

**Files.**
```
src/haandvaerker/services/invoice_monitoring/monitoring_service.py
src/haandvaerker/api/invoice_monitoring.py
tests/test_invoice_overdue_escalation.py
```

**Dependencies.** Phase 1 (cases findes nu i produktion).

**Acceptance criteria.**
1. pytest tests/test_invoice_overdue_escalation.py passerer, inkl.: (a) en aaben case hvis
   due_date er passeret loeftes til priority red; (b) genberegning emitterer priority_raised
   InvoiceEvent KUN naar prioritet faktisk aendres; (c) cases i status
   payment_confirmed/rejected/handled roeres ikke.
2. Endpoint POST /invoice-monitoring/recompute-priorities (eller job i jobs.py -- se aabent
   spoergsmaal 3) genberegner alle aktive aabne cases for company_id og returnerer antal aendrede.
3. Ingen ny status indfoeres (genbrug eksisterende priority-enum + priority_raised event).

**Deletions.** Ingen (ren tilfoejelse -- flaget bevidst).

**Subtraction check.** Kan ikke opnaas ved sletning; men genbruger compute_priority 1:1 og
indfoerer ingen ny status/model.

**Rollback.** Revert commit. Ingen schema-aendring.

**Net LoC intent.** ca. +60 / 0.

### Phase 3: Betalingsbekraeftelse via bank (luk loopet)

**Goal.** Wire den eksisterende reconciliation_bridge til en debet-bankmatcher saa en betalt
kreditor-faktura saettes payment_confirmed, og en haandteret-men-ubetalt faktura forbliver synlig.

**Anchors.** CODE-06, CODE-07, IMPACT-02, OPT-C.

**Files.**
```
src/haandvaerker/services/reconciliation_service.py
src/haandvaerker/services/invoice_monitoring/reconciliation_bridge.py
src/haandvaerker/api/reconciliation.py
tests/test_invoice_payment_confirmation.py
```

**Dependencies.** Phase 1.

**Acceptance criteria.**
1. pytest tests/test_invoice_payment_confirmation.py passerer, inkl.: (a) en debet-
   BankTransaction (amount_ore < 0) der matcher en aaben InvoiceCase paa EKSAKT beloeb +
   payment_reference + dato inden for 7 dage (Antons regel, 2026-06-15) kalder
   confirm_payment -> status payment_confirmed; (b)
   ikke-eksakt match auto-confirmer ALDRIG (Iron Law 3) -- markeres reconciliation_pending /
   kraever human-confirm; (c) ingen match -> case forbliver uaendret og synlig.
2. Soegning paa confirm_payment i src/ viser nu mindst een produktions-caller (ikke kun broen selv).
3. Eksisterende kunde-side reconciliation (EconomicInvoice, CODE-07) er uaendret -- ingen regression.

**Deletions.** Fjern stub-kommentaren i reconciliation_bridge naar broen wires.

**Subtraction check.** Kan ikke opnaas ved sletning; men broen findes allerede -- vi tilfoejer
KUN matcheren, ikke en ny bro.

**Rollback.** Revert commit. Ingen schema-aendring (genbruger BankTransaction + InvoiceCase).

**Net LoC intent.** ca. +90 / -5.

### Phase 4 (valgfri): needs_review-haerdning af risikable ekstraktioner

**Goal.** Relevant faktura med amount_ore==0 eller manglende due_date eskaleres til
needs_review/red i stedet for at glide til gul/groen (luk RISK-01/02).

**Anchors.** RISK-01, RISK-02, OPT-D.

**Files.**
```
src/haandvaerker/services/invoice_monitoring/monitoring_service.py
src/haandvaerker/services/invoice_monitoring/priority.py
tests/test_invoice_needs_review_hardening.py
```

**Dependencies.** Phase 1.

**Acceptance criteria.**
1. pytest tests/test_invoice_needs_review_hardening.py passerer: (a) relevant faktura med
   amount_ore==0 -> status needs_review, ikke payment_required-yellow; (b) relevant faktura
   uden due_date -> priority >= orange.
2. Eksisterende priority-tests passerer uaendret bortset fra de eksplicit aendrede grene.

**Deletions.** Fjern den gren i priority.py der returnerer yellow for amount_ore==0
(erstattes af eskalering).

**Subtraction check.** Delvist ja -- vi fjerner en harmloes-udseende fallback-gren og
erstatter den med synlig eskalering (Iron Law 2).

**Rollback.** Revert commit. Ingen schema-aendring.

**Net LoC intent.** ca. +30 / -5.

## Cross-cutting concerns

- Audit-events: hver tilstandsaendring (fase 1-4) emitter passende InvoiceEvent
  (invoice_case_created, priority_raised, payment_confirmed) -- append-only (vision afsnit 4).
- Idempotens: fase 1 sikrer InboxMessage->InvoiceCase er entydig (RISK-04).
- Multi-tenant: alle nye queries filtrerer paa company_id (CONTRACT-03).
- Migrationer: kun fase 1 har en migration (additiv ALTER, manuel SQL, RISK-03). Verificeres
  med PRAGMA table_info(invoice_case) og SELECT name FROM company foer/efter.
- Tests: hver fase har egen testfil; en integrationstest (kan ligge i fase 3) daekker
  email -> case -> overdue -> betaling -> payment_confirmed.

## Out of scope

- Vi bygger IKKE radaren/datamodellen om -- den findes (CODE-01..03).
- Vi roerer IKKE den udgaaende faktura-verden (Invoice/Payment/InvoiceReminder til kunder).
- Vi roerer IKKE den eksisterende kunde-side reconciliation (EconomicInvoice).
- Vi indfoerer IKKE rigtig LLM-ekstraktion -- regex-stubs beholdes (CONTRACT-04); egen plan.
- Vi tilfoejer IKKE automatisk bankbetaling (Netbank aabnes manuelt, som i dag).
- Vi retter IKKE den latente EntityType-mangel (company_name i LLM-prompt uden enum-vaerdi).
- Vi tilfoejer IKKE notifikationer/email-alarmer ved overdue (kun radar-eskalering) -- senere fase.

## Open questions for the user

1. Ingestion-kilde (RISK-05). InvoiceCase peger i dag paa MailMessage, mens email-polleren
   skriver InboxMessage. Skal vi (a) genbruge InboxMessage direkte som kilde til InvoiceCase
   (anbefales -- undgaar dobbelt-lagring, mindre kode), eller (b) bygge en bro der opretter en
   MailMessage pr. faktura-InboxMessage? Mit forslag i planen er (a).
2. Fase-omfang. Vil du have alle 4 faser, eller kun de 3 kernefaser (1-3) og udskyde
   needs_review-haerdningen (fase 4)?
3. Overdue-mekanisme (OPT-B, fase 2). Skal genberegningen vaere et baggrundsjob (jobs.py
   findes) eller et endpoint der kaldes ved hver radar-visning? Forslag: endpoint nu, job senere.
4. Auto-confirm-praecision (fase 3). Hvilke felter skal kraeves for auto-bekraeftelse af en
   leverandoerbetaling? Forslag: eksakt beloeb + payment_reference-match + dato indenfor 7 dage;
   alt andet kraever manuel bekraeftelse (spejler kunde-siden, CODE-07).

## Review invocation

Efter sidste fase verificerer PASS, invoker review-skillen paa git diff master...HEAD.
Review-skillen vaelger selv reviewer-antal og concerns; forvent faerre reviewere fordi
per-fase deep review allerede er koert.
