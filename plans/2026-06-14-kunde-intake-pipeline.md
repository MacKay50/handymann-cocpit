# Plan: Kunde-intake pipeline

Slug: 2026-06-14-kunde-intake-pipeline
Tier: Complex (full RPIR, 4 faser)
Status: GODKENDT af Anton (2026-06-14) - klar til implementering

## Antons endelige beslutninger (2026-06-14)
1. **UUID i URL:** OK med /forespoergsel?company=<uuid> nu (slug-felt er fremtidig opgave).
2. **Auto-svar:** Ja, kun til kundens egen email.
3. **Database:** INGEN nulstilling. De 3 eksisterende firmaer BEVARES (PLL malerfirma, Gentofte BygningsService, CSKK). Nye kolonner tilfoejes via et manuelt SQL-migrations-script - IKKE reset_demo.bat.
4. **Auto-Enquiry:** Kun for tilbudsforespoergsler (new_quote_request). Fakturaer (invoice_payment) er IKKE i auto-Enquiry-flowet, men maa ALDRIG tabes stille - de skal lande i indbakken med et tydeligt visuelt flag, saa kontordamen ser dem og kan handle. Faktura-haandtering er et separat fremtidigt flow.
5. **Ingen forespoergsel maa tabes:** InboxMessage oprettes ALTID synkront som det primaere artefakt. Alle sekundaere operationer (auto-svar, AI-klassificering, Enquiry-oprettelse) fejler ALDRIG stille - fejl logges paa InboxMessage via processing_error-feltet og kan genafspilles manuelt fra UI. Accept-flow gennemfoeres altid; erfaringsbank-fejl logges men blokerer ikke.

## Maal
Tre indgange (offentlig website-formular, IMAP-email, intern manuel formular) konvergerer til den eksisterende InboxMessage og videre gennem wizard-flowet (classify til Enquiry til convert til Project). Accepterede tilbud faar automatisk en post i erfaringsbanken.

## Arkitektoniske principper
- Et faelles ingest-service-lag (services/inbox_ingest.py) er sandheden for hvordan en ny besked oprettes, klassificeres og evt. bliver til en Enquiry. Alle tre indgange kalder det. (anchor OPTION-02)
- company_id paa det offentlige endpoint kommer som query-param og valideres mod en AKTIV Company. Aldrig i respons. (anchors CODE-03, CONTRACT-01, RISK-02)
- **InboxMessage er det primaere, synkront oprettede artefakt. Det oprettes ALTID foerst og fejler ikke pga. sekundaere trin.** (Antons beslutning 5)
- **Sekundaere trin (auto-svar, klassificering, Enquiry-oprettelse) fejler aldrig stille** (Iron Law 2). En fejl skriver en menneskelaesbar besked til InboxMessage.processing_error og kan genafspilles fra UI. Email-afsendelse maa fejle uden at vaelte forespoergsel-oprettelsen, men logges og rapporteres som sent=false.
- LLM anbefaler, kode beslutter: klassificering er rule-based foerst; lokal-AI er valgfri berigelse.

## Research anchors
- research/2026-06-14-kunde-intake-pipeline/researcher-1-code+contract.json (CODE-01..10, CONTRACT-01..05)
- research/2026-06-14-kunde-intake-pipeline/researcher-2-impact+risk+options.json (IMPACT-01..05, RISK-01..04, OPTION-01..05)
- research/2026-06-14-kunde-intake-pipeline/brief.md

## DB-migrationer (overordnet)
Systemet bruger SQLModel.metadata.create_all, IKKE Alembic (D1=B, CONTRACT-03).
- NYE tabeller (InboxAttachment, fase 3) oprettes automatisk ved boot.
- NYE kolonner paa EKSISTERENDE tabeller (processing_error paa InboxMessage i fase 1; quote_id paa HistoricalOffer i fase 4) tilfoejes IKKE automatisk paa en koerende DB. **De tilfoejes via et manuelt SQL-migrations-script (se fase 4) - IKKE reset_demo.bat. De 3 eksisterende firmaer bevares.** (anchor RISK-01, Antons beslutning 3)

## Fase 1 - Offentlig /forespoergsel + auto-svar + intern manuel formular + tab-sikring

**Anchors.** CODE-01, CODE-02, CODE-03, CODE-04, CODE-05, CONTRACT-01, CONTRACT-02, CONTRACT-04, CONTRACT-05, IMPACT-01, RISK-02, RISK-03, OPTION-01, OPTION-05.

**Hvad bygges.**
- Nyt uautentificeret endpoint POST /forespoergsel med company_id query-param, der opretter InboxMessage(source=website) for den aktive Company via det nye ingest-service-lag (uden klassificering endnu; ingest tager et flag).
- GET /forespoergsel (HTML): simpel offentlig formular (navn, email, telefon, emne, besked) der POSTer til endpointet. Foelger eksisterende static-side-mekanik (CONTRACT-05).
- Auto-svar email til indsenderens egen email via ny acknowledgement-tekst, sendt med eksisterende send-wrapper der aldrig raiser (CODE-05, RISK-03).
- Intern manuel formular i UI der POSTer til eksisterende /intake type=message (company-scoped). Ingen ny backend-route (OPTION-05).
- **Tab-sikring (Antons beslutning 5):** Nyt felt processing_error (str eller None) paa InboxMessage. InboxMessage oprettes ALTID synkront foerst; auto-svar koeres derefter i en try/except der ved fejl skriver kontekst til processing_error (aldrig stille). UI faar en retry-knap der genafspiller de sekundaere trin for en InboxMessage med processing_error.
- **Faktura-flag (Antons beslutning 4):** invoice_payment-beskeder lander i indbakken som InboxMessage og arkiveres ALDRIG stille. De vises med et tydeligt visuelt flag i indbakke-UI (fx roed badge / ikon), saa kontordamen ser dem og kan handle. (Selve auto-klassificeringen der saetter kategorien kommer i fase 2; i fase 1 etableres feltet/visningen, og website-formularens beskeder kan ikke gaa tabt.)

**Fil-aendringer.**
- EDIT models/inbox_message.py (eller tilsvarende model-fil): tilfoej processing_error felt med default None (NY KOLONNE paa eksisterende inboxmessage-tabel - se DB-migration fase 4 for manuel ALTER paa koerende DB).
- NY services/inbox_ingest.py: ingest_message(session, company_id, source, sender felter, subject, body, classify=False) opretter InboxMessage (synkront, primaert) og returnerer den; sekundaere trin wrappes saa fejl logges til processing_error og aldrig boblerer op som tab.
- NY api/forespoergsel.py: router uden auth; POST /forespoergsel med company_id query-param; slaar Company op, validerer active (ens fejl uanset eksistens, RISK-02); kalder ingest + send-acknowledgement; returnerer received=true, acknowledged=bool uden interne IDs (CONTRACT-01).
- EDIT services/wizard_service.py: build_enquiry_acknowledgement(contact_name, company_name) + send-hjaelper der ikke raiser.
- EDIT main.py: include_router(forespoergsel_router) + app.get(/forespoergsel) der serverer static/forespoergsel.html.
- NY static/forespoergsel.html: offentlig formular.
- EDIT static/ui.html (eller ny side): intern manuel intake-formular der POSTer til /intake; indbakke-visning faar (a) visuelt flag for invoice_payment-beskeder og (b) retry-knap for beskeder med processing_error.
- EDIT api/inbox.py: endpoint til at genafspille sekundaere trin (retry) for en InboxMessage med processing_error.
- NY tests/test_forespoergsel.py: client-fixture UDEN get_company_context-override (CONTRACT-04).

**Acceptance criteria.**
1. POST /forespoergsel med gyldig aktiv company_id returnerer 201 og received=true; InboxMessage(source=website) findes.
2. Respons indeholder ALDRIG company_id eller interne IDs.
3. POST med ukendt eller inaktiv company_id giver samme generiske fejl uden at afsloere om UUID findes.
4. POST uden company_id giver 422.
5. Hvis SMTP ikke konfigureret returnerer endpoint stadig 201 med acknowledged=false (email-fejl maskerer ikke oprettelse).
6. GET /forespoergsel returnerer 200 text/html.
7. Intern formular: POST /intake type=message opretter InboxMessage (backend daekket; UI-test verificerer side serveres).
8. **Ingen InboxMessage maa miste data ved fejl i sekundaere trin:** hvis auto-svar (eller andet sekundaert trin) kaster, er InboxMessage stadig oprettet og processing_error udfyldt med menneskelaesbar kontekst (verificeret ved at mocke send-wrapper til at raise).
9. **Retry-knap:** en InboxMessage med processing_error kan genafspille de sekundaere trin via retry-endpointet; ved succes ryddes processing_error.
10. **Faktura-tab-sikring:** en invoice_payment-besked arkiveres aldrig stille - den findes i indbakken og vises med et visuelt flag (UI-test/markup-assertion + backend-felt-assertion).
11. pytest, ruff substance-select og mypy groenne.

**Rollback.** Fjern router-registrering + app.get i main.py; slet nye filer; fjern retry-endpoint. processing_error-kolonnen kan blive staaende (nullable, uskadelig) eller fjernes via manuel ALTER. Ingen reset i fase 1.

## Fase 2 - Automatisk klassificering + Enquiry-oprettelse

**Anchors.** CODE-06, CODE-07, CODE-08, IMPACT-02, IMPACT-03, RISK-04, OPTION-02, OPTION-03.

**Hvad bygges.**
- Udvid inbox_ingest.ingest_message til (a) altid at koere rule-based classify_message og persistere MessageClassification+MessageEntity (idempotent), og (b) auto-oprette Enquiry KUN naar primary_category er new_quote_request og msg.enquiry_id er None (RISK-04, OPTION-03). (Antons beslutning 4: kun tilbudsforespoergsler.)
- **invoice_payment giver INGEN auto-Enquiry, men beskeden bevares og faar det visuelle flag fra fase 1** (Antons beslutning 4 - fakturaer maa aldrig tabes stille).
- **Klassificering er et sekundaert trin:** hvis classify fejler, oprettes/bevares InboxMessage stadig, og fejlen skrives til processing_error (Antons beslutning 5) - aldrig stille tab.
- Udtraek Enquiry-oprettelsen fra inbox.convert_to_enquiry til en delt funktion saa manuel og auto bruger samme kode (CODE-07).
- Kald ingest med classify=True fra alle tre indgange (IMAP poll, /intake, /forespoergsel).
- I poll-stien bruges KUN rule-based klassificering (ingen synkron lokal-AI per email) for at undgaa lange poll-tider (IMPACT-03).

**Fil-aendringer.**
- EDIT services/inbox_ingest.py: classify+persist+auto-enquiry; parameter use_llm=False default; classify wrappet saa fejl gaar til processing_error.
- EDIT api/inbox.py: refaktorer convert_to_enquiry til at kalde delt create_enquiry_from_message.
- EDIT email_poller.py: kald ingest-klassificering (rule-based) efter oprettelse.
- EDIT api/intake.py og api/forespoergsel.py: saet classify=True.
- EDIT tests: test_message_classifications, test_inbox, test_email_poller, test_forespoergsel.

**Acceptance criteria.**
1. Ny InboxMessage via enhver indgang faar automatisk en MessageClassification.
2. new_quote_request giver automatisk Enquiry(status=new) med msg.enquiry_id sat.
3. spam eller invoice_payment giver INGEN auto-Enquiry.
4. invoice_payment-besked bevares i indbakken og baerer det visuelle flag (tabes aldrig stille).
5. Gentaget ingest af samme besked giver ikke dubleret klassificering eller Enquiry.
6. Manuel POST /inbox/{id}/convert virker stadig og deler kode med auto-stien.
7. poll_inbox kalder ikke lokal-AI synkront per email (mock-verificeret).
8. Hvis classify kaster, er InboxMessage stadig oprettet og processing_error udfyldt (ingen stille tab).
9. pytest, ruff substance-select og mypy groenne.

**Rollback.** Saet classify=False i de tre kaldssteder; manuel classify+convert virker som foer. Ingen DB-aendring.

## Fase 3 - Vedhaeftningshaandtering (IMAP + haandvaerker-upload)

**Anchors.** CODE-08, CODE-09, IMPACT-04, CONTRACT-03.

**Hvad bygges.**
- NY tabel InboxAttachment (oprettes automatisk af create_all - ny tabel).
- IMAP-udtraek: poll_inbox gemmer email-vedhaeftninger som filer + InboxAttachment-raekker.
- Haandvaerker-upload: POST /inbox/{message_id}/attachments (company-scoped) der modtager UploadFile, foelger company_logo-moenster (suffix-allowlist, MAX_SIZE_BYTES, UUID-filnavn, gem under static/uploads/attachments/), opretter InboxAttachment (IMPACT-04).
- GET /inbox/{message_id}/attachments.

**Fil-aendringer.**
- NY models/inbox_attachment.py: InboxAttachment(id, company_id FK, inbox_message_id FK, filename, content_type, size_bytes, storage_path, created_at) + Read-schema.
- EDIT email_poller.py: gem vedhaeftninger (parts med Content-Disposition attachment); allowlist + stoerrelsesgraense; UUID-filnavn; opret InboxAttachment.
- EDIT api/inbox.py: POST/GET attachments-endpoints (company-scoped).
- EDIT main.py: sikr static/uploads/attachments oprettes i lifespan; importer ny model saa create_all ser den.
- NY tests/test_inbox_attachments.py.

**Acceptance criteria.**
1. POST /inbox/{id}/attachments med tilladt fil returnerer 201; InboxAttachment-raekke med UUID-baseret storage_path under static/uploads/attachments/.
2. Ikke-tilladt filtype giver 422; fil over MAX_SIZE_BYTES giver 422.
3. Gemt filnavn paa disk er IKKE afsenderens raa filename (path-traversal-vagt); visningsnavn bevares i filename-kolonnen.
4. IMAP-poll af email med vedhaeftning opretter baade InboxMessage og tilknyttet InboxAttachment.
5. GET /inbox/{id}/attachments lister kun den companys vedhaeftninger (cross-company giver 403/tom).
6. pytest, ruff substance-select og mypy groenne.

**Rollback.** Fjern attachments-endpoints + poller-udtraek. Ny tabel kan staa tom (uskadelig) eller fjernes ved DB-reset. Ingen aendring paa eksisterende tabeller.

## Fase 4 - Erfaringsbank-link ved tilbudsaccept + manuelt SQL-migrations-script

**Anchors.** CODE-10, IMPACT-05, RISK-01, OPTION-04, CONTRACT-03.

**Hvad bygges.**
- NY valgfri kolonne quote_id paa HistoricalOffer.
- Ved tilbudsaccept oprettes automatisk en HistoricalOffer fra det accepterede tilbud med deterministisk felt-mapping (titel; price_ex_vat/vat/price_inc_vat fra quote.subtotal/vat_amount/total; areal fra rum hvis quote_type er area), extraction_status=approved, accepted_status=accepted, company_id=quote.company_id, quote_id=quote.id. Idempotent paa quote_id (OPTION-04).
- Faelles service-funktion kaldes fra BEGGE accept-stier (accept_quote og accept_by_token) (IMPACT-05).
- **Erfaringsbank-fejl blokerer ALDRIG accept** (Antons beslutning 5): create_historical_offer_from_quote wrappes, accept gennemfoeres altid, fejl logges. Iron Law 2 - aldrig stille tab, men accept maa ikke vaelte.

**Fil-aendringer.**
- EDIT models/historical_offer.py: quote_id Optional med default None, indexeret. (NY KOLONNE paa eksisterende tabel.)
- NY services/offer_from_quote.py: create_historical_offer_from_quote(session, quote) med deterministisk mapping; idempotent paa quote_id.
- EDIT api/quotes.py: kald funktionen i accept_quote (efter faktura-oprettelse) og i accept_by_token; wrappet saa fejl ikke blokerer accept.
- NY tests/test_offer_from_quote.py + udvid test_quote_acceptance.py.
- NY migrations/2026-06-14-add-columns.sql (manuelt SQL-script - se DB-migration nedenfor).

**DB-migration (KRITISK, RISK-01 - Antons beslutning 3: INGEN nulstilling).**
De nye kolonner (processing_error paa inboxmessage fra fase 1, quote_id paa historicaloffer fra fase 4) tilfoejes IKKE automatisk af create_all paa den koerende haandvaerker.db. **reset_demo.bat maa IKKE bruges** - de 3 eksisterende firmaer skal bevares:
- **PLL (malerfirma)**
- **Gentofte BygningsService**
- **CSKK**

I stedet leveres et manuelt SQL-migrations-script (migrations/2026-06-14-add-columns.sql) der koeres een gang mod haandvaerker.db. Scriptet dokumenterer at en duplicate-column-fejl mod en frisk DB (hvor modellen allerede har kolonnen) er ufarlig, alternativt bruges en guard. Konkret indhold:

    -- Fase 1: tab-sikring paa inbox
    ALTER TABLE inboxmessage ADD COLUMN processing_error VARCHAR;
    -- Fase 4: erfaringsbank-link
    ALTER TABLE historicaloffer ADD COLUMN quote_id VARCHAR;

Koerselsmaade (dokumenteres i scriptets header): koer scriptet mod haandvaerker.db med sqlite3, eller via et lille python-snippet der aabner samme DB-fil som appen. Verificer bagefter at de 3 firmaer stadig findes (SELECT name FROM company foer og efter). Tests rammes ikke (frisk in-memory create_all har allerede kolonnerne via modellen).

**Acceptance criteria.**
1. accept_quote (intern) opretter praecis een HistoricalOffer med quote_id sat, extraction_status=approved, accepted_status=accepted og priser der matcher tilbuddet.
2. accept_by_token (offentlig) opretter ligeledes en HistoricalOffer via samme delte funktion.
3. Gentaget accept opretter IKKE en dublet (idempotent paa quote_id).
4. Arealbaseret tilbud udfylder area-felter fra rum; linjebaseret efterlader dem None (ingen fabrikerede tal, Iron Law 2).
5. Den oprettede HistoricalOffer ses i GET /historical-offers.
6. **Erfaringsbank-fejl blokerer ikke accept:** hvis create_historical_offer_from_quote kaster, gennemfoeres accept stadig og fejlen logges (verificeret ved mock der raiser).
7. **Migrations-scriptet** tilfoejer begge kolonner til en kopi af en realistisk DB UDEN at slette/aendre eksisterende firma-data (verificeret: de 3 firmaer findes foer og efter).
8. pytest, ruff substance-select og mypy groenne.

**Rollback.** Fjern kaldet i begge accept-stier. quote_id- og processing_error-kolonnerne kan blive staaende (nullable, uskadelige) - ingen reset. Oprettede poster kan deaktiveres (active=false).

## Out of scope (hele planen)
- SMS-indgang (eksplicit udeladt).
- Slug-baserede offentlige URLs (kraever Company.slug + migration; separat opgave) (OPTION-01).
- Rate-limiting, CAPTCHA, honeypot paa det offentlige endpoint (opfoelgning; IMPACT-01).
- Lokal-AI-berigelse i IMAP-poll-stien (kun rule-based der) (IMPACT-03).
- Indfoersel af Alembic (systemet koerer paa create_all, D1=B). Separat strukturel opgave.
- Embeddings/semantisk soegning paa accept-genererede HistoricalOffers.
- Kunde-login / kundeportal (vision: kunder logger ikke ind).
- **Faktura-haandtering (analyse, restance-forebyggelse, automatisk handling paa invoice_payment).** I denne plan sikres KUN at fakturaer ikke tabes stille (visuelt flag i indbakken). Selve faktura-flowet er et separat fremtidigt projekt. (Antons beslutning 4.)

## Loeste spoergsmaal (Antons svar 2026-06-14)
1. company_id i URL: OK med UUID nu (slug-felt er fremtidig). (OPTION-01)
2. Auto-svar: kun til kundens egen email. (RISK-03)
3. DB: INGEN reset. Manuelt SQL-migrations-script; PLL, Gentofte BygningsService og CSKK bevares. (RISK-01)
4. Auto-Enquiry: kun new_quote_request. invoice_payment faar visuelt flag, tabes aldrig stille; faktura-flow er separat fremtidigt. (OPTION-03)
5. Tab-sikring: InboxMessage altid primaert + synkront; sekundaere trin fejler aldrig stille (processing_error + retry); accept blokeres aldrig af erfaringsbank-fejl. (IMPACT-05)
