# vision.md — Håndværker Business System

## What this is

Et internt styringssystem til en lille håndværkervirksomhed (2-8 ansatte).
Systemet samler alle forretningsdata pr. kunde: tilbud, projekter, tidsregistrering,
udlæg, fakturaer, betalinger, møder og dokumenter. Medarbejdere logger timer og udlæg
fra telefonen; ejeren håndterer økonomi, fakturering og indberetninger fra en
webgrænseflade. Alt er bundet op på en kunde og et projekt.

## Why it exists

Tidligere lå tilbud i email, timer på papirslapper, udlæg i en skokasse og fakturaer
i et regneark. Det gav dobbeltindtastning, tabte bilag og fakturafejl. Virksomheden
har brug for ét sted der hænger alt sammen — fra første kundehenvendelse til afsluttet
regnskab og løn — uden at kræve dyrt ERP-system eller revisorassistance til
hverdagsopgaver.

## Design principles

1. **Kunden er omdrejningspunktet.** Alle data tilhører en kunde → et projekt.
   Intet timer-entry, tilbud, faktura eller dokument eksisterer uden et projekt-id.

2. **LLM anbefaler, kode beslutter.** Alle konsekvensbeslutninger (fakturabeløb,
   lønsats, momsberegning) træffes af deterministisk kode. LLM-funktioner bruges
   kun til kladder og opsummering.

3. **Fejl er synlige.** Ingen stille defaults på forretningskritiske felter
   (beløb, dato, moms). Mangler → valideringsfejl med besked, aldrig 0-værdier.

4. **Revisionsspor på økonomi.** Fakturaer, betalinger og lønposteringer er
   append-only (soft-delete). Historik slettes aldrig — kun deaktiveres.

5. **Flad struktur — ingen plugin-magi.** Nye ressourcer registreres ét sted
   (router-fil + model-fil). Ingen dynamisk class-loading.

6. **Følsomme data maskeres ved output.** CVR/CPR-numre og bankkontonumre
   forlader aldrig API-svaret i klartekst til browseren. Altid maskeret
   (f.eks. `****1234`).

7. **Design for nem ændring.** Enhver ikke-triviel ændring efterlader systemet
   bedre struktureret end før. Policy adskilt fra transport. Config adskilt fra kode.

8. **Offline-venlig for feltbrug.** Timer og udlæg kan registreres via PWA og
   synkroniseres ved næste netforbindelse. API'et er idempotent på client-genererede
   UUIDs.

## What this is NOT

- Dette er ikke et fuldt regnskabsprogram. Det eksporterer data til e-conomic /
  Billy / Dinero — det erstatter dem ikke.
- Dette er ikke en lønseddel-generator. Det beregner timegrundlag og sender til
  lønsystem (Zenegy / Dataløn) — det udsteder ikke lønsedler selv.
- Dette er ikke et dokumentarkiv. Bilag gemmes som fil-referencer; storage er
  ekstern (S3 / lokalt filsystem).
- Vi kæder ikke LLM-agenter i loops uden deterministiske gates. Hvert model-kald
  har et kode-tjekket output.
- Dette er ikke et kundefront-system. Kunder logger ikke ind — kun virksomhedens
  egne medarbejdere.

## Current status

Greenfield. Datamodel og REST API for kunder, projekter, tilbud og tidsregistrering
er under udvikling (se `plans/`). Ikke startet: fakturamodul, lønsystem-integration,
skat-indberetning, PWA-shell, regnskabseksport. Ingen produktionsdata endnu.
