#!/usr/bin/env python3
"""
Demo seed-script — PLL Malerfirma ApS + KarateKlub + Bygningsservice.

Kræver at serveren kører:  python -m uvicorn haandvaerker.main:app --reload

Valgfrie parametre (overrides fixture-filer):
  --bank-csv     <sti>   Bankudtog fra Danske Bank (DD-MM-YYYY eller DD.MM.YYYY)
  --invoice-csv  <sti>   Faktura-eksport fra e-conomic
  --customer-csv <sti>   Kundekartotek-eksport fra e-conomic

Eksempel:
  python seed_demo.py --bank-csv C:\\Afstemning\\bank_maj_2026.csv ^
                      --invoice-csv C:\\Afstemning\\fakturaer_2026.csv ^
                      --customer-csv C:\\Afstemning\\kunder.csv
"""
import argparse
import sys
import io
import pathlib
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import httpx

BASE = "http://127.0.0.1:8000"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Seed demo-data til Håndværker Business System")
    p.add_argument("--bank-csv",     default=None, metavar="STI", help="Bankudtog CSV (Danske Bank)")
    p.add_argument("--invoice-csv",  default=None, metavar="STI", help="e-conomic faktura-eksport CSV")
    p.add_argument("--customer-csv", default=None, metavar="STI", help="e-conomic kundekartotek CSV")
    return p.parse_args()


_args = _parse_args()


def _check():
    try:
        httpx.get(BASE, timeout=3)
    except Exception:
        print()
        print("  FEJL: Serveren kører ikke på http://127.0.0.1:8000")
        print("  Start den først:  start.bat  (eller dobbeltklik på start.bat)")
        print()
        sys.exit(1)


def post(path, data=None):
    r = httpx.post(f"{BASE}{path}", json=data or {}, timeout=10)
    if r.status_code not in (200, 201):
        print(f"\n  FEJL {r.status_code} på POST {path}")
        print(f"  {r.text[:300]}")
        sys.exit(1)
    return r.json()


def ok(msg):
    print(f"  >>  {msg}")


# ─────────────────────────────────────────────────────────────────────────────

_check()

print()
print("=" * 62)
print("  SEED-SCRIPT  —  PLL Malerfirma ApS")
print("=" * 62)
print()

# ── 1. Virksomhed ─────────────────────────────────────────────────────────────
print("[ 1/11 ]  Virksomhed")
co = post("/companies/", {
    "name": "PLL Malerfirma ApS",
    "address": "Malervejen 5, 2100 København Ø",
    "cvr": "12345678",
})
vid = co["id"]
ok(f"{co['name']}  (CVR 12345678)")

# ── 2. Medarbejdere ───────────────────────────────────────────────────────────
print("[ 2/11 ]  Medarbejdere")
lars = post("/employees/", {"name": "Lars Pedersen",  "default_hourly_rate": 500.0, "company_id": vid})
anne = post("/employees/", {"name": "Anne Lund",      "default_hourly_rate": 450.0, "company_id": vid})
ok(f"{lars['name']}  —  500 kr/t")
ok(f"{anne['name']}  —  450 kr/t")

# ── 3. Kunder ─────────────────────────────────────────────────────────────────
print("[ 3/11 ]  Kunder")
hansen    = post("/customers/", {"name": "Familie Hansen",           "address": "Villavej 12, 2900 Hellerup",              "company_id": vid})
vesterbro = post("/customers/", {"name": "Boligforeningen Vesterbro","address": "Vesterbrogade 100, 1620 København V",     "company_id": vid})
kronborg  = post("/customers/", {"name": "Restaurant Kronborg",      "address": "Strandgade 5, 3000 Helsingør",           "company_id": vid})
ok(hansen["name"])
ok(vesterbro["name"])
ok(kronborg["name"])

# ── 4. Projekter ──────────────────────────────────────────────────────────────
print("[ 4/11 ]  Projekter")
p_stue       = post("/projects/", {"title": "Stue + køkken",         "customer_id": hansen["id"]})
p_facade     = post("/projects/", {"title": "Facaderenovering",       "customer_id": vesterbro["id"]})
p_restaurant = post("/projects/", {"title": "Restaurantlokale",       "customer_id": kronborg["id"]})
p_sove       = post("/projects/", {"title": "Soveværelse",            "customer_id": hansen["id"]})
ok(f"'{p_stue['title']}'  →  Familie Hansen")
ok(f"'{p_facade['title']}'  →  Boligforeningen Vesterbro")
ok(f"'{p_restaurant['title']}'  →  Restaurant Kronborg")
ok(f"'{p_sove['title']}'  →  Familie Hansen")

# ── 5. Tilbud: stue+køkken — accepteret → faktura sendt ──────────────────────
print("[ 5/11 ]  Tilbud stue + køkken  (accepteret, faktura sendt)")
q_stue = post("/quotes/", {
    "project_id": p_stue["id"],
    "title": "Tilbud – Malerarbejde stue og køkken",
    "valid_until": "2026-06-15",
    "notes": "Inkluderer grunding, to lag maling og afslibning af lister.",
    "lines": [
        {"description": "Malerarbejde stue — 2 lag",   "unit": "time", "quantity": 16.0, "unit_price": 500.0},
        {"description": "Malerarbejde køkken — 2 lag", "unit": "time", "quantity":  8.0, "unit_price": 500.0},
        {"description": "Maling og materialer",         "unit": "stk",  "quantity":  1.0, "unit_price": 1800.0},
    ],
})
post(f"/quotes/{q_stue['id']}/send")
acc = post(f"/quotes/{q_stue['id']}/accept")
inv_stue_id = acc["invoice_id"]
post(f"/invoices/{inv_stue_id}/send")
ok(f"{q_stue['quote_number']}  accepteret  →  faktura auto-oprettet og sendt")
ok(f"Faktura total: {(16+8)*500 + 1800} kr ekskl. moms")

# ── 6. Tilbud: restaurantlokale — sendt, afventer svar ───────────────────────
print("[ 6/11 ]  Tilbud restaurantlokale  (afventer accept)")
q_kron = post("/quotes/", {
    "project_id": p_restaurant["id"],
    "title": "Tilbud – Ommaling af restaurantlokale",
    "valid_until": "2026-06-01",
    "notes": "Prisen er inkl. alle materialer. Arbejdet udføres uden for åbningstid.",
    "lines": [
        {"description": "Ommaling vægge og loft",  "unit": "m2",  "quantity": 180.0, "unit_price":  85.0},
        {"description": "Maling, grunding, ruller", "unit": "stk", "quantity":   1.0, "unit_price": 2400.0},
    ],
})
post(f"/quotes/{q_kron['id']}/send")
ok(f"{q_kron['quote_number']}  sendt  —  afventer svar fra Restaurant Kronborg")

# ── 7. Soveværelse — accepteret + betalt ──────────────────────────────────────
print("[ 7/11 ]  Soveværelse  (afsluttet, faktura betalt)")
q_sove = post("/quotes/", {
    "project_id": p_sove["id"],
    "title": "Tilbud – Soveværelse",
    "lines": [
        {"description": "Malerarbejde soveværelse", "unit": "time", "quantity":  8.0, "unit_price": 500.0},
        {"description": "Materialer",               "unit": "stk",  "quantity":  1.0, "unit_price": 600.0},
    ],
})
post(f"/quotes/{q_sove['id']}/send")
acc2 = post(f"/quotes/{q_sove['id']}/accept")
inv_sove_id = acc2["invoice_id"]
post(f"/invoices/{inv_sove_id}/send")
post(f"/invoices/{inv_sove_id}/pay")
ok(f"{q_sove['quote_number']}  accepteret  →  faktura sendt og betalt")

# ── 8. Timer på facaderenovering ──────────────────────────────────────────────
print("[ 8/11 ]  Timer  —  Facaderenovering")
entries = [
    ("2026-05-05", lars["id"], 8.0),
    ("2026-05-06", lars["id"], 8.0),
    ("2026-05-07", anne["id"], 6.0),
    ("2026-05-08", lars["id"], 8.0),
    ("2026-05-09", anne["id"], 8.0),
    ("2026-05-12", lars["id"], 6.0),
]
for d, eid, h in entries:
    post("/time-entries/", {"project_id": p_facade["id"], "employee_id": eid,
                             "date": d, "hours": h, "billable": True})
total_h = sum(h for _, _, h in entries)
ok(f"{total_h} timer registreret  (Lars + Anne, uge 19–20)")

# ── 9. Udgifter på facaderenovering ───────────────────────────────────────────
print("[ 9/11 ]  Udgifter  —  Facaderenovering")
post("/expenses/", {"project_id": p_facade["id"], "employee_id": lars["id"],
                     "category": "materialer", "date": "2026-05-05",
                     "description": "Facademaling og grunding — 2 x 10L", "amount_excl_vat": 3400.0})
post("/expenses/", {"project_id": p_facade["id"], "employee_id": anne["id"],
                     "category": "parkering", "date": "2026-05-07",
                     "description": "P-hus Vesterbro, 2 dage", "amount_excl_vat": 75.0})
post("/expenses/", {"project_id": p_facade["id"], "employee_id": lars["id"],
                     "category": "materialer", "date": "2026-05-12",
                     "description": "Afspritning og tape", "amount_excl_vat": 280.0})
ok("Materialer  3.400 kr  +  280 kr")
ok("Parkering   75 kr")

# Saml facade-udlæg i faktura-kladde
facade_inv = post("/invoices/draft-from-project", {
    "project_id": p_facade["id"],
    "issue_date": "2026-05-20",
    "due_date":   "2026-06-19",
    "title": "Faktura – Facaderenovering",
})
ok(f"Faktura-kladde samlet: {facade_inv['invoice_number']}")

# ── 10. Årshjul 2026 ──────────────────────────────────────────────────────────
print("[10/11 ]  Årshjul 2026")
post("/admin-deadlines/generate-year", {"company_id": vid, "year": 2026})
ok("Momsfrister, lønkørsler, årsregnskab, selskabsskat, forsikring")

# ── 11. Aftaler ───────────────────────────────────────────────────────────────
print("[11/12 ]  Aftaler  —  kalender-demo")

# Afsluttet: Afsluttende gennemgang stue (fortid)
ap1 = post("/appointments/", {
    "company_id": vid, "project_id": p_stue["id"],
    "title": "Afsluttende gennemgang — Stue + køkken",
    "appointment_type": "site_visit",
    "start_datetime": "2026-05-14T15:00:00", "end_datetime": "2026-05-14T16:00:00",
    "location": "Villavej 12, 2900 Hellerup",
    "notes": "Kunden gennemgår det færdige arbejde og godkender.",
})
post(f"/appointments/{ap1['id']}/complete")
ok("14. maj  —  Gennemgang stue (afsluttet)")

# Byggemøde facaderenovering (denne uge)
post("/appointments/", {
    "company_id": vid, "project_id": p_facade["id"], "employee_id": lars["id"],
    "title": "Byggemøde — Facaderenovering uge 21",
    "appointment_type": "meeting",
    "start_datetime": "2026-05-21T08:00:00", "end_datetime": "2026-05-21T09:00:00",
    "location": "Vesterbrogade 100, 1620 København V",
    "notes": "Status på fremskridt, planlæg resterende arbejde.",
})
ok("21. maj  —  Byggemøde facaderenovering (Lars)")

# Besigtigelse ny forespørgsel — badeværelse Morten
post("/appointments/", {
    "company_id": vid,
    "title": "Besigtigelse — Badeværelse & gang, Morten Christensen",
    "appointment_type": "site_visit",
    "start_datetime": "2026-05-22T10:00:00", "end_datetime": "2026-05-22T11:00:00",
    "location": "Frederiksberg Allé 23, 2000 Frederiksberg",
    "notes": "Forespørgsel fra indbakken. Vurder omfang og prissæt.",
})
ok("22. maj  —  Besigtigelse badeværelse (ny kunde)")

# Personalemøde
post("/appointments/", {
    "company_id": vid, "employee_id": lars["id"],
    "title": "Personalemøde — Planlægning juni",
    "appointment_type": "meeting",
    "start_datetime": "2026-05-23T08:00:00", "end_datetime": "2026-05-23T09:00:00",
    "location": "Kontoret",
    "notes": "Gennemgang af igangværende projekter og ferie-planlægning.",
})
ok("23. maj  —  Personalemøde (planlægning juni)")

# Tilbudsmøde Østerbro lejlighed (Lise Borg fra indbakken)
post("/appointments/", {
    "company_id": vid, "employee_id": lars["id"],
    "title": "Tilbudsmøde — Lejlighed Østerbrogade (Lise Borg)",
    "appointment_type": "estimate",
    "start_datetime": "2026-05-27T13:00:00", "end_datetime": "2026-05-27T14:00:00",
    "location": "Østerbrogade 87, 2100 København Ø",
    "notes": "4-rums lejlighed, 110m². Alle rum inkl. lofter. Tag tilbudsmateriale med.",
})
ok("27. maj  —  Tilbudsmøde Østerbro (Lise Borg)")

# Opfølgning restaurant Kronborg — afventer svar på tilbud
post("/appointments/", {
    "company_id": vid, "project_id": p_restaurant["id"],
    "title": "Opfølgning på tilbud — Restaurant Kronborg",
    "appointment_type": "meeting",
    "start_datetime": "2026-06-02T10:00:00", "end_datetime": "2026-06-02T10:30:00",
    "location": "Telefonmøde",
    "notes": f"Tilbud {q_kron['quote_number']} sendt — afklaring og eventuel justering.",
})
ok("2. jun   —  Opfølgning Restaurant Kronborg (tilbud)")

# Opstart facaderenovering (fremtid, næste fase)
post("/appointments/", {
    "company_id": vid, "project_id": p_facade["id"], "employee_id": anne["id"],
    "title": "Opstart — Facaderenovering, phase 2 (nordgavl)",
    "appointment_type": "site_visit",
    "start_datetime": "2026-06-09T07:00:00", "end_datetime": "2026-06-09T08:00:00",
    "location": "Vesterbrogade 100, 1620 København V",
    "notes": "Anne starter nordgavl. Kontroller at stilladser er klar.",
})
ok("9. jun   —  Opstart phase 2 facaderenovering (Anne)")

# ── 12. Indbakke ──────────────────────────────────────────────────────────────
print("[12/12 ]  Indbakke  —  2 ulæste beskeder")
post("/inbox/", {
    "company_id": vid, "source": "phone",
    "sender_name": "Morten Christensen", "sender_phone": "22 33 44 55",
    "subject": "Forespørgsel om tilbud — badeværelse",
    "body": "Hej, vil gerne have et tilbud på maling af badeværelse og gang. Lejlighed på ca. 85m². Ring gerne tilbage.",
    "received_at": "2026-05-19T09:15:00",
})
post("/inbox/", {
    "company_id": vid, "source": "email",
    "sender_name": "Lise Borg", "sender_email": "lise.borg@example.dk",
    "subject": "Tilbud på lejlighed — Østerbro",
    "body": "Vi er ved at renovere vores lejlighed (4 rum, 110m²) og søger malerfirma til hele lejligheden inkl. lofter.",
    "received_at": "2026-05-20T08:00:00",
})
ok("Morten Christensen  —  badeværelse (telefon)")
ok("Lise Borg  —  lejlighed Østerbro (e-mail)")

# ── 13. Bankafstemning — demo-data ────────────────────────────────────────────
print("[13/15 ]  Bankafstemning  —  bankudtog + e-conomic fakturaer")
_fixtures = pathlib.Path(__file__).parent / "tests" / "fixtures"
_bank_csv = _args.bank_csv    or str(_fixtures / "danske_bank_sample.csv")
_inv_csv  = _args.invoice_csv or str(_fixtures / "economic_invoices_sample.csv")
if _args.bank_csv:
    ok(f"Bruger brugerleveret bankudtog: {_args.bank_csv}")
if _args.invoice_csv:
    ok(f"Bruger brugerleveret faktura-eksport: {_args.invoice_csv}")

r_bank = httpx.post(f"{BASE}/bank-transactions/import",
                    params={"company_id": vid, "file_path": _bank_csv}, timeout=10)
if r_bank.status_code != 201:
    print(f"\n  FEJL {r_bank.status_code} på bank-import"); print(f"  {r_bank.text[:300]}"); sys.exit(1)

r_inv = httpx.post(f"{BASE}/economic-invoices/import",
                   params={"company_id": vid, "file_path": _inv_csv}, timeout=10)
if r_inv.status_code != 201:
    print(f"\n  FEJL {r_inv.status_code} på faktura-import"); print(f"  {r_inv.text[:300]}"); sys.exit(1)

r_match = httpx.post(f"{BASE}/reconciliation/match", params={"company_id": vid}, timeout=10)
if r_match.status_code != 201:
    print(f"\n  FEJL {r_match.status_code} på afstemning"); print(f"  {r_match.text[:300]}"); sys.exit(1)

n = r_match.json()
ok(f"Bankudtog: {r_bank.json()['rows_imported']} transaktioner")
ok(f"e-conomic: {r_inv.json()['rows_imported']} fakturaer")
ok(f"Auto-match: {n['deterministic_count']} par  —  3 kræver handling")
ok("Se /reconciliation for overblik")

# ── 14. e-conomic kundekartotek ───────────────────────────────────────────────
print("[14/15 ]  e-conomic kundekartotek  —  import + sync + repeat-job")
_ec_csv = _args.customer_csv or str(_fixtures / "economic_customers_sample.csv")
if _args.customer_csv:
    ok(f"Bruger brugerleveret kundekartotek: {_args.customer_csv}")

r_ec = httpx.post(f"{BASE}/economic-customers/import",
                  params={"company_id": vid, "file_path": _ec_csv}, timeout=10)
if r_ec.status_code != 201:
    print(f"\n  FEJL {r_ec.status_code} på e-conomic kundeimport")
    print(f"  {r_ec.text[:300]}")
    sys.exit(1)

r_sync = httpx.post(f"{BASE}/economic-customers/sync-all",
                    params={"company_id": vid}, timeout=10)
if r_sync.status_code != 200:
    print(f"\n  FEJL {r_sync.status_code} på sync-all")
    print(f"  {r_sync.text[:300]}")
    sys.exit(1)

sync = r_sync.json()
ok(f"e-conomic import: {r_ec.json()['rows_imported']} kunder fra CSV")
ok(f"Sync-all: {sync['matched']} matchede  |  {sync['created']} oprettede  |  {sync['skipped']} sprunget over")
if sync["warnings"]:
    for w in sync["warnings"]:
        ok(f"  Advarsel: {w}")

r_rj = httpx.post(f"{BASE}/customers/{hansen['id']}/repeat-job",
                   params={"title": "Gentagelses-opgave Villavej 12"}, timeout=10)
if r_rj.status_code != 201:
    print(f"\n  FEJL {r_rj.status_code} på repeat-job")
    print(f"  {r_rj.text[:300]}")
    sys.exit(1)
rj = r_rj.json()
ok(f"Repeat-job: '{rj['project']['title']}'  →  {rj['quote']['quote_number']} (kladde)")

# ── 15. Fuld pipeline ─────────────────────────────────────────────────────────
print("[15/15 ]  Pipeline  —  kunder fra fakturaer → historiske projekter")

r_derive = httpx.post(f"{BASE}/economic-invoices/derive-customers",
                      params={"company_id": vid}, timeout=10)
if r_derive.status_code != 200:
    print(f"\n  FEJL {r_derive.status_code} på derive-customers"); print(f"  {r_derive.text[:300]}"); sys.exit(1)
d = r_derive.json()
ok(f"Kunder udledt fra fakturanavne: {d['created']} nye  |  {d['linked']} fakturaer linket  |  {d['already_linked']} allerede linket")

r_hist = httpx.post(f"{BASE}/economic-invoices/create-historical-projects",
                    params={"company_id": vid}, timeout=10)
if r_hist.status_code != 201:
    print(f"\n  FEJL {r_hist.status_code} på create-historical-projects"); print(f"  {r_hist.text[:300]}"); sys.exit(1)
h = r_hist.json()
ok(f"Historiske projekter oprettet: {h['created']}  (én pr. bankbekræftet faktura)")
if h["skipped"]:
    for s in h["skipped"]:
        ok(f"  Sprunget over: {s}")
ok("Loopet lukket: faktura → kunde → projekt (afsluttet)")

# ══════════════════════════════════════════════════════════════
# VIRKSOMHED 2 — Charlottenlund Shotokan KarateKlub
# ══════════════════════════════════════════════════════════════
print()
print("=" * 62)
print("  SEED  —  Charlottenlund Shotokan KarateKlub")
print("=" * 62)

karate = post("/companies/", {
    "name": "Charlottenlund Shotokan KarateKlub",
    "address": "Klampenborgvej 14, 2920 Charlottenlund",
    "cvr": "23456789",
})
kid = karate["id"]
ok(f"{karate['name']}  (CVR 23456789)")

henrik = post("/employees/", {"name": "Henrik Møller",   "default_hourly_rate": 375.0, "company_id": kid, "title": "Cheftræner"})
maria  = post("/employees/", {"name": "Maria Andersen",  "default_hourly_rate": 300.0, "company_id": kid, "title": "Kasserer"})
ok(f"{henrik['name']}  —  Cheftræner")
ok(f"{maria['name']}   —  Kasserer")

k_eriksen  = post("/customers/", {"name": "Familien Eriksen",              "address": "Strandvejen 88, 2920 Charlottenlund", "company_id": kid})
k_kommune  = post("/customers/", {"name": "Gentofte Kommune",              "address": "Bernstorffsvej 161, 2920 Charlottenlund", "company_id": kid})
k_erhverv  = post("/customers/", {"name": "Erhvervsklubben Nordsjælland",  "address": "Lyngby Hovedgade 10, 2800 Lyngby",     "company_id": kid})
ok(k_eriksen["name"])
ok(k_kommune["name"])
ok(k_erhverv["name"])

p_sommerstævne = post("/projects/", {"title": "Sommerstævne 2026",          "customer_id": k_kommune["id"],  "company_id": kid})
p_dojo         = post("/projects/", {"title": "Renovering af dojo",         "customer_id": k_eriksen["id"], "company_id": kid})
p_firmafitness = post("/projects/", {"title": "Firmafitness — Erhvervsklubben", "customer_id": k_erhverv["id"], "company_id": kid})
ok(f"'{p_sommerstævne['title']}'")
ok(f"'{p_dojo['title']}'")
ok(f"'{p_firmafitness['title']}'")

# Tilbud + faktura — dojo-renovering
q_dojo = post("/quotes/", {
    "project_id": p_dojo["id"],
    "title": "Tilbud — Renovering og maling af dojo",
    "valid_until": "2026-06-30",
    "lines": [
        {"description": "Maling af vægge og loft, dojo",  "unit": "m2",  "quantity": 120.0, "unit_price":  90.0},
        {"description": "Gulvlak (3 lag), tatami-område", "unit": "m2",  "quantity":  60.0, "unit_price": 145.0},
        {"description": "Materialer og afspritning",      "unit": "stk", "quantity":   1.0, "unit_price": 1200.0},
    ],
})
post(f"/quotes/{q_dojo['id']}/send")
acc_dojo = post(f"/quotes/{q_dojo['id']}/accept")
post(f"/invoices/{acc_dojo['invoice_id']}/send")
ok(f"{q_dojo['quote_number']}  accepteret  →  faktura sendt")

# Tilbud — firmafitness (afventer svar)
q_ff = post("/quotes/", {
    "project_id": p_firmafitness["id"],
    "title": "Tilbud — Firmafitness-program, 3 mdr.",
    "valid_until": "2026-06-01",
    "lines": [
        {"description": "Holdtræning, 2 x ugentligt, 3 mdr.", "unit": "stk", "quantity": 24.0, "unit_price": 850.0},
        {"description": "Personlig introduktion (x10 pers.)", "unit": "stk", "quantity":  1.0, "unit_price": 2500.0},
    ],
})
post(f"/quotes/{q_ff['id']}/send")
ok(f"{q_ff['quote_number']}  sendt  —  afventer Erhvervsklubben")

post("/admin-deadlines/generate-year", {"company_id": kid, "year": 2026})
ok("Årshjul 2026 genereret")

# Aftaler
ap_k1 = post("/appointments/", {
    "company_id": kid, "project_id": p_dojo["id"], "employee_id": henrik["id"],
    "title": "Besigtigelse — Dojo før renovering",
    "appointment_type": "site_visit",
    "start_datetime": "2026-05-16T10:00:00", "end_datetime": "2026-05-16T11:00:00",
    "location": "Klampenborgvej 14, Charlottenlund",
    "notes": "Opmål og vurder omfang. Aftale med håndværker.",
})
post(f"/appointments/{ap_k1['id']}/complete")
ok("16. maj  —  Besigtigelse dojo (afsluttet)")

post("/appointments/", {
    "company_id": kid, "employee_id": henrik["id"],
    "title": "Træner-møde — Sæsonprogram efterår 2026",
    "appointment_type": "meeting",
    "start_datetime": "2026-05-24T09:00:00", "end_datetime": "2026-05-24T11:00:00",
    "location": "Klubhuset",
    "notes": "Planlæg holdopdeling, stævnekalender og instruktørvagter.",
})
ok("24. maj  —  Trænermøde sæsonprogram")

post("/appointments/", {
    "company_id": kid, "project_id": p_sommerstævne["id"],
    "title": "Koordineringsmøde — Sommerstævne 2026",
    "appointment_type": "meeting",
    "start_datetime": "2026-06-05T14:00:00", "end_datetime": "2026-06-05T15:30:00",
    "location": "Gentofte Rådhus",
    "notes": "Lokaleaftale, sikkerhed, frivillige og tidsplan med kommunen.",
})
ok("5. jun   —  Koordinering sommerstævne (kommune)")

post("/appointments/", {
    "company_id": kid, "project_id": p_firmafitness["id"], "employee_id": henrik["id"],
    "title": "Opstartsmøde — Firmafitness, Erhvervsklubben",
    "appointment_type": "estimate",
    "start_datetime": "2026-06-16T12:00:00", "end_datetime": "2026-06-16T13:00:00",
    "location": "Lyngby Hovedgade 10",
    "notes": "Præsentation af program, holdstørrelser og betalingsplan.",
})
ok("16. jun  —  Opstartsmøde firmafitness")

post("/inbox/", {
    "company_id": kid, "source": "email",
    "sender_name": "Pia Eriksen", "sender_email": "pia.eriksen@example.dk",
    "subject": "Tilmelding — børnehold september",
    "body": "Hej, vi vil gerne tilmelde vores søn (9 år) til begynderholdet til september. Hvad koster det og hvornår er der plads?",
    "received_at": "2026-05-20T11:30:00",
})
ok("Indbakke: Pia Eriksen — børnetilmelding")

# ══════════════════════════════════════════════════════════════
# VIRKSOMHED 3 — Gentofte Bygningsservice 69
# ══════════════════════════════════════════════════════════════
print()
print("=" * 62)
print("  SEED  —  Gentofte Bygningsservice 69")
print("=" * 62)

byg = post("/companies/", {
    "name": "Gentofte Bygningsservice 69",
    "address": "Gentoftegade 69, 2820 Gentofte",
    "cvr": "34567890",
})
bid = byg["id"]
ok(f"{byg['name']}  (CVR 34567890)")

bjarne  = post("/employees/", {"name": "Bjarne Kristiansen", "default_hourly_rate": 625.0, "company_id": bid, "title": "Mester"})
susanne = post("/employees/", {"name": "Susanne Holm",        "default_hourly_rate": 400.0, "company_id": bid, "title": "Projektleder"})
thomas  = post("/employees/", {"name": "Thomas Vang",         "default_hourly_rate": 550.0, "company_id": bid, "title": "Håndværker"})
ok(f"{bjarne['name']}   —  Mester, 625 kr/t")
ok(f"{susanne['name']}  —  Projektleder, 400 kr/t")
ok(f"{thomas['name']}   —  Håndværker, 550 kr/t")

b_andels  = post("/customers/", {"name": "Andelsboligforeningen Søndergaard", "address": "Søndergaardsvej 4, 2820 Gentofte",   "company_id": bid})
b_cafe    = post("/customers/", {"name": "Café Paradis",                       "address": "Ordrupvej 62, 2920 Charlottenlund", "company_id": bid})
b_knud    = post("/customers/", {"name": "Knud Larsen",                        "address": "Tranegårdsvej 21, 2900 Hellerup",   "company_id": bid})
b_skole   = post("/customers/", {"name": "Tranegård Skole",                    "address": "Tranegårdsvej 58, 2900 Hellerup",   "company_id": bid})
ok(b_andels["name"])
ok(b_cafe["name"])
ok(b_knud["name"])
ok(b_skole["name"])

p_tag     = post("/projects/", {"title": "Tagudskiftning — Blok C",          "customer_id": b_andels["id"], "company_id": bid})
p_koekken = post("/projects/", {"title": "Køkkenrenovering",                  "customer_id": b_cafe["id"],   "company_id": bid})
p_badevaer= post("/projects/", {"title": "Badeværelse — totalrenovering",     "customer_id": b_knud["id"],   "company_id": bid})
p_skole   = post("/projects/", {"title": "Vedligeholdelse — facader og tag",  "customer_id": b_skole["id"],  "company_id": bid})
ok(f"'{p_tag['title']}'       →  {b_andels['name']}")
ok(f"'{p_koekken['title']}'    →  {b_cafe['name']}")
ok(f"'{p_badevaer['title']}'  →  {b_knud['name']}")
ok(f"'{p_skole['title']}'  →  {b_skole['name']}")

# Tagudskiftning — tilbud sendt, accepteret, faktura sendt
q_tag = post("/quotes/", {
    "project_id": p_tag["id"],
    "title": "Tilbud — Tagudskiftning Blok C, Søndergaard",
    "valid_until": "2026-06-15",
    "notes": "Inkluderer stillads, bortskaffelse af gammelt tag og 30 års garanti.",
    "lines": [
        {"description": "Nedtagning eksisterende tagbelægning", "unit": "m2",  "quantity": 280.0, "unit_price":  95.0},
        {"description": "Ny tagbelægning inkl. underlag",       "unit": "m2",  "quantity": 280.0, "unit_price": 380.0},
        {"description": "Tagrende og nedløb, komplet",          "unit": "lm",  "quantity":  48.0, "unit_price": 320.0},
        {"description": "Stillads, opstilling og nedtagning",   "unit": "stk", "quantity":   1.0, "unit_price": 18500.0},
    ],
})
post(f"/quotes/{q_tag['id']}/send")
acc_tag = post(f"/quotes/{q_tag['id']}/accept")
post(f"/invoices/{acc_tag['invoice_id']}/send")
ok(f"{q_tag['quote_number']}  accepteret  →  faktura sendt")

# Badeværelse — tilbud afventer
q_bad = post("/quotes/", {
    "project_id": p_badevaer["id"],
    "title": "Tilbud — Badeværelse totalrenovering, Larsen",
    "valid_until": "2026-06-01",
    "lines": [
        {"description": "Nedrivning og bortskaffelse",    "unit": "stk", "quantity":  1.0, "unit_price":  8500.0},
        {"description": "VVS — ny installation",          "unit": "stk", "quantity":  1.0, "unit_price": 22000.0},
        {"description": "Flisesætning vægge (20m²)",      "unit": "m2",  "quantity": 20.0, "unit_price":   650.0},
        {"description": "Gulvfliser m. gulvvarme (5m²)",  "unit": "m2",  "quantity":  5.0, "unit_price":   890.0},
        {"description": "Malerarbejde og afslutning",     "unit": "stk", "quantity":  1.0, "unit_price":  4200.0},
    ],
})
post(f"/quotes/{q_bad['id']}/send")
ok(f"{q_bad['quote_number']}  sendt  —  afventer Knud Larsen")

# Skole — kladdefaktura
q_skole = post("/quotes/", {
    "project_id": p_skole["id"],
    "title": "Tilbud — Vedligeholdelse facader og tag 2026",
    "lines": [
        {"description": "Facaderens og fugecheck",     "unit": "m2",  "quantity": 450.0, "unit_price":  45.0},
        {"description": "Malerbehandling vinduer (24)","unit": "stk", "quantity":  24.0, "unit_price": 780.0},
        {"description": "Taginspektion og reparation", "unit": "stk", "quantity":   1.0, "unit_price": 6500.0},
    ],
})
post(f"/quotes/{q_skole['id']}/send")
acc_skole = post(f"/quotes/{q_skole['id']}/accept")
ok(f"{q_skole['quote_number']}  accepteret  →  faktureringskladde klar")

post("/admin-deadlines/generate-year", {"company_id": bid, "year": 2026})
ok("Årshjul 2026 genereret")

# Tidsregistreringer — tagudskiftning
for d, eid, h in [
    ("2026-05-11", bjarne["id"], 8.0), ("2026-05-12", bjarne["id"], 8.0),
    ("2026-05-12", thomas["id"], 8.0), ("2026-05-13", bjarne["id"], 6.0),
    ("2026-05-13", thomas["id"], 8.0), ("2026-05-14", thomas["id"], 8.0),
    ("2026-05-19", bjarne["id"], 8.0), ("2026-05-19", thomas["id"], 8.0),
    ("2026-05-20", thomas["id"], 8.0),
]:
    post("/time-entries/", {"project_id": p_tag["id"], "employee_id": eid,
                             "date": d, "hours": h, "billable": True})
ok("70 timer registreret på tagudskiftning (Bjarne + Thomas)")

# Aftaler
ap_b1 = post("/appointments/", {
    "company_id": bid, "project_id": p_badevaer["id"], "employee_id": bjarne["id"],
    "title": "Besigtigelse — Badeværelse, Knud Larsen",
    "appointment_type": "site_visit",
    "start_datetime": "2026-05-15T09:00:00", "end_datetime": "2026-05-15T10:00:00",
    "location": "Tranegårdsvej 21, 2900 Hellerup",
    "notes": "Opmål badeværelse. Kunde ønsker totalrenovering.",
})
post(f"/appointments/{ap_b1['id']}/complete")
ok("15. maj  —  Besigtigelse badeværelse Larsen (afsluttet)")

post("/appointments/", {
    "company_id": bid, "project_id": p_tag["id"], "employee_id": bjarne["id"],
    "title": "Opstartsmøde — Tagudskiftning Søndergaard",
    "appointment_type": "meeting",
    "start_datetime": "2026-05-21T07:30:00", "end_datetime": "2026-05-21T08:30:00",
    "location": "Søndergaardsvej 4, Gentofte",
    "notes": "Gennemgang med bestyrelsen. Bekræft start og nabovarsel.",
})
ok("21. maj  —  Opstartsmøde tagudskiftning")

post("/appointments/", {
    "company_id": bid, "project_id": p_skole["id"], "employee_id": susanne["id"],
    "title": "Byggemøde — Facadevedligeholdelse, Tranegård Skole",
    "appointment_type": "meeting",
    "start_datetime": "2026-05-28T10:00:00", "end_datetime": "2026-05-28T11:00:00",
    "location": "Tranegårdsvej 58, Hellerup",
    "notes": "Koordiner med skolens vicevært. Arbejde uden for undervisningstid.",
})
ok("28. maj  —  Byggemøde Tranegård Skole (Susanne)")

post("/appointments/", {
    "company_id": bid, "project_id": p_koekken["id"], "employee_id": bjarne["id"],
    "title": "Tilbudsmøde — Køkkenrenovering, Café Paradis",
    "appointment_type": "estimate",
    "start_datetime": "2026-06-03T13:00:00", "end_datetime": "2026-06-03T14:00:00",
    "location": "Ordrupvej 62, Charlottenlund",
    "notes": "Præsenter løsning for nyt erhvervskøkken. Arbejde udføres om natten.",
})
ok("3. jun   —  Tilbudsmøde Café Paradis")

post("/appointments/", {
    "company_id": bid, "employee_id": bjarne["id"],
    "title": "Leverandørmøde — Tagmaterialer, Icopal",
    "appointment_type": "meeting",
    "start_datetime": "2026-06-10T09:00:00", "end_datetime": "2026-06-10T10:00:00",
    "location": "Telefonmøde",
    "notes": "Priser på næste leverance. Forhandl rabat ved volumen > 500m².",
})
ok("10. jun  —  Leverandørmøde Icopal")

post("/inbox/", {
    "company_id": bid, "source": "email",
    "sender_name": "Dorthe Sørensen", "sender_email": "d.sorensen@example.dk",
    "subject": "Forespørgsel — murværk og fuger, Hellerup",
    "body": "Hej, vi har et ældre parcelhus fra 1962 med problemer med fuger og murværk. Kan I komme og se på det? Vi bor i Hellerup.",
    "received_at": "2026-05-20T14:20:00",
})
post("/inbox/", {
    "company_id": bid, "source": "phone",
    "sender_name": "Jan Holmberg", "sender_phone": "40 50 60 70",
    "subject": "Akut tagskade efter storm",
    "body": "Ring tilbage ASAP. Taget er gået op efter gårsdagens storm. Vand trænger ind. Adressen er Jægersborg Allé 32.",
    "received_at": "2026-05-21T07:05:00",
})
ok("Indbakke: Dorthe Sørensen — murværk/fuger")
ok("Indbakke: Jan Holmberg — akut tagskade")

# ── Opsummering ────────────────────────────────────────────────────────────────
print()
print("=" * 62)
print("  DEMO-DATA KLAR  —  3 virksomheder")
print("=" * 62)
print()
print("  PLL Malerfirma ApS")
print("   • 2 medarbejdere  |  3 kunder    |  4 projekter")
print("   • 3 tilbud        |  3 fakturaer |  7 aftaler")
print("   • 3 e-conomic kunder importeret  |  1 repeat-job oprettet")
print("   • Fuld pipeline: fakturaer → kunder → historiske projekter")
print()
print("  Charlottenlund Shotokan KarateKlub")
print("   • 2 medarbejdere  |  3 kunder    |  3 projekter")
print("   • 2 tilbud        |  1 faktura   |  4 aftaler")
print()
print("  Gentofte Bygningsservice 69")
print("   • 3 medarbejdere  |  4 kunder    |  4 projekter")
print("   • 3 tilbud        |  2 fakturaer |  5 aftaler")
print()
print("  Links:")
print("  Dashboard:  http://127.0.0.1:8000/ui")
print("  Swagger:    http://127.0.0.1:8000/docs")
print()
print(f"  PLL Malerfirma:   http://127.0.0.1:8000/ui?company_id={vid}")
print(f"  KarateKlub:       http://127.0.0.1:8000/ui?company_id={kid}")
print(f"  Bygningsservice:  http://127.0.0.1:8000/ui?company_id={bid}")
print("=" * 62)
print()
