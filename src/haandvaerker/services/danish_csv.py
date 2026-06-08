from __future__ import annotations

import csv
import datetime as _dt
import hashlib
import io
from datetime import date

import openpyxl
from pydantic import BaseModel

from ..models.bank_transaction import BankTransactionCreate, BankTransactionStatus
from ..models.economic_invoice import EconomicInvoiceCreate
from ..models.economic_customer import EconomicCustomerCreate


class ImportResult(BaseModel):
    rows_imported: int
    rows_skipped: int
    errors: list[str]


def decode_csv_bytes(raw: bytes) -> str:
    """Try UTF-8-sig → UTF-8 → CP-1252 → Latin-1. Latin-1 maps all 256 bytes so it never fails."""
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    # unreachable — latin-1 always succeeds
    raise ValueError("Kunne ikke dekode CSV-fil")


def parse_danish_date(s: str) -> date:
    """Parse DD-MM-YYYY or DD.MM.YYYY (Danske Bank exports both). Raises ValueError."""
    s = s.strip()
    # Normalise separator: dots and dashes are both common in Danish bank exports
    normalised = s.replace(".", "-")
    try:
        day, month, year = normalised.split("-")
        return date(int(year), int(month), int(day))
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"Ugyldig dato '{s}' — forventet DD-MM-YYYY eller DD.MM.YYYY") from exc


def parse_danish_amount_ore(s: str) -> int:
    """
    Parse Danish amount string to integer øre.

    '1.234,56' -> 123456
    '-1.234,56' -> -123456
    '0,01' -> 1
    '12345,67' -> 1234567
    """
    s = s.strip().replace(".", "").replace(",", ".")
    try:
        return round(float(s) * 100)
    except ValueError as exc:
        raise ValueError(f"Ugyldigt beløb '{s}'") from exc


def _row_import_hash(
    company_id: str, transaction_date: date, amount_ore: int, description: str
) -> str:
    """SHA-256 hex of normalised content for deduplication."""
    content = (
        f"{company_id}|{transaction_date.isoformat()}|{amount_ore}|"
        f"{description.strip().lower()}"
    )
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _detect_bank_columns(header: list[str]) -> dict[str, int | None]:
    """
    Map logical column names to indices by inspecting the header row.

    Supports multiple Danske Bank export variants:
      Classic (4 col):  Bogfoeringsdato ; Tekst     ; Beloeb ; Saldo
      With currency (5): Bogfoeringsdato ; Tekst     ; Beloeb ; Valuta ; Saldo
      With value date:   Bogfoeringsdato ; Vaerdidato; Tekst  ; Beloeb ; Valuta ; Saldo
      Currency first:    Bogfoeringsdato ; Tekst     ; Valuta ; Beloeb ; Saldo

    Falls back to positional (0=date, 1=desc, 2=amount, 3=balance) for unknown headers.
    """
    # Normalise: strip, lowercase, remove BOM
    normalised = [h.strip().lower().lstrip("﻿") for h in header]

    _DATE_NAMES   = {"bogfoeringsdato", "dato", "date", "bookingdate"}
    _DESC_NAMES   = {"tekst", "text", "beskrivelse", "description", "posteringstekst"}
    _AMT_NAMES    = {"beloeb", "beløb", "amount", "beloeb (dkk)", "beløb (dkk)"}
    _BAL_NAMES    = {"saldo", "saldo (dkk)", "balance"}
    _BESKED_NAMES = {"besked", "meddelelse", "note", "betalingstekst", "tekst 2", "tekst2"}
    # Valuta / currency columns are deliberately omitted — we skip them

    col_date = col_desc = col_amt = col_bal = col_besked = None
    for i, name in enumerate(normalised):
        if name in _DATE_NAMES and col_date is None:
            col_date = i
        elif name in _DESC_NAMES and col_desc is None:
            col_desc = i
        elif name in _AMT_NAMES and col_amt is None:
            col_amt = i
        elif name in _BAL_NAMES and col_bal is None:
            col_bal = i
        elif name in _BESKED_NAMES and col_besked is None:
            col_besked = i

    # Positional fallback when header names are unrecognised
    if col_date is None:
        col_date = 0
    if col_desc is None:
        # Skip value-date column if it looks like a date (second column)
        col_desc = 2 if len(normalised) > 2 and normalised[1] in {"vaerdidato", "valuedato"} else 1
    if col_amt is None:
        col_amt = col_desc + 1
    # col_bal and col_besked stay None — optional

    return {"date": col_date, "desc": col_desc, "amt": col_amt, "bal": col_bal, "besked": col_besked}


def parse_danske_bank_csv(
    content: str, company_id: str
) -> tuple[list[BankTransactionCreate], list[str]]:
    """
    Parse Danske Bank semicolon-delimited CSV.

    Auto-detects column positions from the header row so all common Danske Bank
    export variants are handled (with/without Valuta column, with/without Vaerdidato).

    Returns (rows, errors). If errors is non-empty, rows is empty (all-or-nothing).
    """
    reader = csv.reader(io.StringIO(content), delimiter=";")
    rows: list[BankTransactionCreate] = []
    errors: list[str] = []
    col_map: dict[str, int | None] | None = None

    for row_index, fields in enumerate(reader):
        if col_map is None:
            # First row is always the header
            col_map = _detect_bank_columns(fields)
            continue

        file_line = row_index + 1

        if not any(f.strip() for f in fields):
            continue

        try:
            max_needed = max(col_map["date"], col_map["desc"], col_map["amt"])
            if len(fields) <= max_needed:
                raise ValueError(
                    f"For få kolonner: forventede mindst {max_needed + 1}, fik {len(fields)}"
                )

            date_str    = fields[col_map["date"]]
            description = fields[col_map["desc"]]
            amount_str  = fields[col_map["amt"]]
            bal_idx     = col_map["bal"]
            balance_str = fields[bal_idx] if bal_idx is not None and len(fields) > bal_idx else None

            besked_idx = col_map.get("besked")
            if besked_idx is not None and len(fields) > besked_idx:
                besked_val = fields[besked_idx].strip()
                if besked_val and besked_val != description.strip():
                    description = (description.strip() + " | " + besked_val)[:490]

            transaction_date = parse_danish_date(date_str)
            amount_ore = parse_danish_amount_ore(amount_str)
            balance_ore: int | None = None
            if balance_str and balance_str.strip():
                balance_ore = parse_danish_amount_ore(balance_str)

            import_hash = _row_import_hash(company_id, transaction_date, amount_ore, description)

            rows.append(
                BankTransactionCreate(
                    company_id=company_id,
                    transaction_date=transaction_date,
                    description=description,
                    amount_ore=amount_ore,
                    balance_ore=balance_ore,
                    import_hash=import_hash,
                    status=BankTransactionStatus.unmatched,
                )
            )
        except ValueError as exc:
            errors.append(f"Linje {file_line}: {exc}")

    if errors:
        return [], errors
    return rows, []


def parse_economic_invoice_csv(
    content: str, company_id: str
) -> tuple[list[EconomicInvoiceCreate], list[str]]:
    """
    Parse e-conomic invoice export CSV.

    Expected header:
        Fakturanummer;Debitor;Nettobeloeb;Momsbeloeb;Bruttobeloeb;Forfaldsdato;Bogfoeringsdato

    Returns (rows, errors). If errors is non-empty, rows is empty (all-or-nothing).
    """
    reader = csv.reader(io.StringIO(content), delimiter=";")
    rows: list[EconomicInvoiceCreate] = []
    errors: list[str] = []

    header_skipped = False
    for row_index, fields in enumerate(reader):
        if not header_skipped:
            header_skipped = True
            continue

        # File line number (1-based, header=1): row_index + 1
        file_line = row_index + 1

        if not any(f.strip() for f in fields):
            continue

        try:
            if len(fields) < 7:
                raise ValueError(
                    f"For få kolonner: forventede 7, fik {len(fields)}"
                )
            invoice_number = fields[0].strip()
            customer_name = fields[1].strip()
            net_str = fields[2]
            vat_str = fields[3]
            gross_str = fields[4]
            due_date_str = fields[5]
            invoice_date_str = fields[6]

            net_amount_ore = parse_danish_amount_ore(net_str)
            vat_amount_ore = parse_danish_amount_ore(vat_str)
            gross_amount_ore = parse_danish_amount_ore(gross_str)
            due_date = parse_danish_date(due_date_str)
            invoice_date = parse_danish_date(invoice_date_str)

            rows.append(
                EconomicInvoiceCreate(
                    company_id=company_id,
                    economic_invoice_number=invoice_number,
                    customer_name=customer_name,
                    net_amount_ore=net_amount_ore,
                    vat_amount_ore=vat_amount_ore,
                    gross_amount_ore=gross_amount_ore,
                    invoice_date=invoice_date,
                    due_date=due_date,
                )
            )
        except ValueError as exc:
            errors.append(f"Linje {file_line}: {exc}")

    if errors:
        return [], errors
    return rows, []


def _detect_invoice_columns(header: list[str]) -> dict[str, int | None]:
    """
    Map logical e-conomic invoice column names to indices from header row.

    Handles multiple e-conomic export layouts:
      - Standard invoice export: Fakturanummer;Debitor;Netto;Moms;Brutto;Forfaldsdato;Bogfoeringsdato
      - Unpaid invoices report:  Aktuel forfaldsdato;...;Fakturanr.;Faktura forfaldsdato;...;Beløb;...;Kundenavn;...

    Returns dict where col_vat and col_date may be None:
      - col_vat is None  → caller sets vat_amount_ore = 0
      - col_date is None → caller uses due_date as invoice_date
    """
    normalised = [h.strip().lower().lstrip("﻿") for h in header]

    _NUM_NAMES   = {
        "fakturanummer", "bilagsnummer", "fakturanr.", "fakturanr", "faktura nr.",
        "faktura nr", "invoice number", "invoice no.", "invoice no", "nr.",
    }
    _CUST_NAMES  = {
        "debitor", "kundenavn", "debitornavn", "kunde", "customer", "navn", "name",
    }
    _NET_NAMES   = {
        "netto", "nettobeloeb", "nettobeløb", "nettoomsætning",
        "netto (dkk)", "nettobeløb (dkk)", "net", "net amount",
    }
    _VAT_NAMES   = {
        "moms", "momsbeloeb", "momsbeløb", "moms (dkk)", "momsbeløb (dkk)", "vat", "tax",
    }
    _GROSS_NAMES = {
        "brutto", "bruttobeloeb", "bruttobeløb",
        "brutto (dkk)", "bruttobeløb (dkk)", "gross", "total",
        # e-conomic debt/unpaid reports use a single total amount column:
        "beloeb", "beløb", "restbeloeb", "restbeløb",
    }
    _DUE_NAMES   = {
        "forfaldsdato", "forfald", "due date", "forfalder", "betalingsfrist",
        "faktura forfaldsdato",  # e-conomic unpaid invoices report
    }
    _DATE_NAMES  = {
        "bogfoeringsdato", "bogføringsdato", "fakturadato", "dato",
        "bogf. dato", "bogf.dato", "invoice date",
    }

    col_num = col_cust = col_net = col_vat = col_gross = col_due = col_date = None
    for i, name in enumerate(normalised):
        if name in _NUM_NAMES and col_num is None:         col_num = i
        elif name in _CUST_NAMES and col_cust is None:     col_cust = i
        elif name in _NET_NAMES and col_net is None:       col_net = i
        elif name in _VAT_NAMES and col_vat is None:       col_vat = i
        elif name in _GROSS_NAMES and col_gross is None:   col_gross = i
        elif name in _DUE_NAMES and col_due is None:       col_due = i
        elif name in _DATE_NAMES and col_date is None:     col_date = i

    # Positional fallbacks for standard CSV format
    if col_num is None:   col_num = 0
    if col_cust is None:  col_cust = 1

    # Amount fallbacks: when only gross is found (single-amount file), reuse it for net
    if col_gross is not None and col_net is None:
        col_net = col_gross
    elif col_net is None:
        col_net = 2
    if col_gross is None:
        col_gross = 4

    # col_vat stays None when missing → caller defaults to 0
    if col_due is None:   col_due = 5
    # col_date stays None when missing → caller defaults to due_date

    return {
        "num": col_num, "cust": col_cust, "net": col_net,
        "vat": col_vat, "gross": col_gross, "due": col_due, "date": col_date,
    }


def _fix_invoice_col_map_by_types(
    col_map: dict[str, int | None],
    first_data_row: tuple,
) -> dict[str, int | None]:
    """
    Validate that amount columns contain numeric data, not dates.

    If col_map["net"] points to a date cell, the header scan did not recognise
    the column names. Rebuild the amount/date assignment from actual cell types,
    using the already-detected text/number columns (num, cust) as anchors so
    invoice numbers stored as integers are not mistaken for amounts.
    """
    if not first_data_row:
        return col_map
    net_idx = col_map["net"]
    if net_idx is None or net_idx >= len(first_data_row):
        return col_map
    net_val = first_data_row[net_idx]
    if not isinstance(net_val, (_dt.date, _dt.datetime)):
        return col_map  # mapping already looks correct

    # Amount column contains a date — header names were unrecognised for amounts.
    # Exclude anchors (invoice number col, customer col) from the candidate scan so
    # integer invoice numbers are not confused with monetary amounts.
    anchors = {col_map.get("num"), col_map.get("cust")}
    numeric_candidates = [
        i for i, v in enumerate(first_data_row)
        if i not in anchors and isinstance(v, (int, float))
    ]
    date_candidates = [
        i for i, v in enumerate(first_data_row)
        if isinstance(v, (_dt.date, _dt.datetime))
    ]

    patched = dict(col_map)
    if len(numeric_candidates) >= 3:
        patched["net"], patched["vat"], patched["gross"] = (
            numeric_candidates[0], numeric_candidates[1], numeric_candidates[2]
        )
    elif len(numeric_candidates) >= 1:
        patched["gross"] = numeric_candidates[-1]
        if len(numeric_candidates) >= 2:
            patched["net"] = numeric_candidates[0]

    # Only reassign date cols if header detection also failed them
    if len(date_candidates) >= 2:
        if patched.get("due") not in date_candidates:
            patched["due"] = date_candidates[0]
        if patched.get("date") not in date_candidates:
            patched["date"] = date_candidates[1] if len(date_candidates) > 1 else date_candidates[0]

    return patched


def _cell_str(val: object) -> str:
    return "" if val is None else str(val).strip()


def _cell_amount_ore(val: object, label: str) -> int:
    """Accept both numeric (xlsx) and Danish-formatted string (csv) cell values."""
    if isinstance(val, (int, float)):
        return round(float(val) * 100)
    s = _cell_str(val)
    if not s:
        raise ValueError(f"Tomt beløb i kolonne '{label}'")
    return parse_danish_amount_ore(s)


def _cell_date(val: object, label: str) -> date:
    """Accept datetime objects (xlsx) and formatted strings (csv/xlsx)."""
    if isinstance(val, _dt.datetime):
        return val.date()
    if isinstance(val, _dt.date):
        return val
    s = _cell_str(val)
    if not s:
        raise ValueError(f"Tom dato i kolonne '{label}'")
    return parse_danish_date(s)


def parse_economic_invoice_xlsx(
    raw: bytes, company_id: str
) -> tuple[list[EconomicInvoiceCreate], list[str]]:
    """
    Parse e-conomic invoice export XLSX.

    Auto-detects column positions from the header row (handles Danish/English column names).
    Accepts numeric cell values for amounts and date objects for dates — both common in
    e-conomic Excel exports.

    Returns (rows, errors). If errors is non-empty, rows is empty (all-or-nothing).
    """
    try:
        wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    except Exception as exc:
        return [], [f"Kan ikke åbne XLSX-fil: {exc}"]

    ws = wb.active
    all_rows = list(ws.iter_rows(values_only=True))
    wb.close()

    if not all_rows:
        return [], ["XLSX-filen er tom"]

    # Find header row: scan up to first 10 rows for a row containing a known invoice column name
    _HEADER_SIGNALS = {
        "fakturanummer", "bilagsnummer", "fakturanr.", "fakturanr",
        "debitor", "kundenavn", "debitornavn", "invoice number",
    }
    header_idx = 0
    for i, row in enumerate(all_rows[:10]):
        row_lower = {str(c).strip().lower() for c in row if c is not None}
        if row_lower & _HEADER_SIGNALS:
            header_idx = i
            break

    header = [_cell_str(c) for c in all_rows[header_idx]]
    col_map = _detect_invoice_columns(header)

    # Validate mapping against first data row — fixes layouts where header names
    # were not recognised and the positional fallback landed on date columns
    first_data = next(
        (r for r in all_rows[header_idx + 1:] if any(c is not None for c in r)),
        (),
    )
    col_map = _fix_invoice_col_map_by_types(col_map, first_data)

    # Determine max column index needed (skip None optional columns)
    required_idxs = [col_map["num"], col_map["cust"], col_map["net"], col_map["gross"], col_map["due"]]
    optional_idxs = [col_map["vat"], col_map["date"]]
    max_needed = max(i for i in required_idxs if i is not None)

    rows_out: list[EconomicInvoiceCreate] = []
    errors: list[str] = []

    for excel_row_num, raw_row in enumerate(all_rows[header_idx + 1:], start=header_idx + 2):
        if not any(c is not None and str(c).strip() for c in raw_row):
            continue

        try:
            if len(raw_row) <= max_needed:
                raise ValueError(
                    f"For få kolonner: forventede mindst {max_needed + 1}, fik {len(raw_row)}"
                )

            invoice_number = _cell_str(raw_row[col_map["num"]])
            customer_name  = _cell_str(raw_row[col_map["cust"]])
            if not invoice_number:
                raise ValueError("Fakturanummer er tomt")
            if not customer_name:
                raise ValueError("Debitor er tomt")

            net_amount_ore   = _cell_amount_ore(raw_row[col_map["net"]],   "Netto")
            gross_amount_ore = _cell_amount_ore(raw_row[col_map["gross"]], "Brutto")
            # vat: optional — files with only a total Beløb column get vat=0
            vat_col = col_map["vat"]
            vat_amount_ore = (
                _cell_amount_ore(raw_row[vat_col], "Moms")
                if vat_col is not None and vat_col < len(raw_row)
                else 0
            )
            due_date     = _cell_date(raw_row[col_map["due"]], "Forfaldsdato")
            # invoice_date: optional — fall back to due_date when column is absent
            date_col = col_map["date"]
            invoice_date = (
                _cell_date(raw_row[date_col], "Bogfoeringsdato")
                if date_col is not None and date_col < len(raw_row)
                else due_date
            )

            rows_out.append(
                EconomicInvoiceCreate(
                    company_id=company_id,
                    economic_invoice_number=str(invoice_number),
                    customer_name=customer_name,
                    net_amount_ore=net_amount_ore,
                    vat_amount_ore=vat_amount_ore,
                    gross_amount_ore=gross_amount_ore,
                    invoice_date=invoice_date,
                    due_date=due_date,
                )
            )
        except ValueError as exc:
            errors.append(f"Række {excel_row_num}: {exc}")

    if errors:
        return [], errors
    return rows_out, []


def _normalize_cvr(raw: str) -> str | None:
    """Strip non-digit characters; return 8-digit string or None."""
    digits = "".join(c for c in raw if c.isdigit())
    if len(digits) == 8:
        return digits
    return None


def parse_economic_customer_csv(
    content: str, company_id: str
) -> tuple[list[EconomicCustomerCreate], list[str]]:
    """
    Parse e-conomic customer export CSV.

    Expected header:
        Kundenummer;Navn;Adresse;Postnummer;By;CVR;Email;Telefon

    Returns (rows, errors). If errors is non-empty, rows is empty (all-or-nothing).
    """
    reader = csv.reader(io.StringIO(content), delimiter=";")
    rows: list[EconomicCustomerCreate] = []
    errors: list[str] = []

    header_skipped = False
    for row_index, fields in enumerate(reader):
        if not header_skipped:
            header_skipped = True
            continue

        # File line number (1-based, header=1): row_index + 1
        file_line = row_index + 1

        if not any(f.strip() for f in fields):
            continue

        try:
            if len(fields) < 2:
                raise ValueError(
                    f"For få kolonner: forventede mindst 2, fik {len(fields)}"
                )
            economic_customer_number = fields[0].strip()
            if not economic_customer_number:
                raise ValueError("Kundenummer må ikke være tomt")

            name = fields[1].strip()
            if len(name) < 1:
                raise ValueError("Navn må ikke være tomt")

            address = fields[2].strip() if len(fields) > 2 and fields[2].strip() else None
            postal_code = fields[3].strip() if len(fields) > 3 and fields[3].strip() else None
            city = fields[4].strip() if len(fields) > 4 and fields[4].strip() else None

            cvr_raw = fields[5].strip() if len(fields) > 5 else ""
            cvr_number = _normalize_cvr(cvr_raw) if cvr_raw else None

            email = fields[6].strip() if len(fields) > 6 and fields[6].strip() else None
            phone = fields[7].strip() if len(fields) > 7 and fields[7].strip() else None

            rows.append(
                EconomicCustomerCreate(
                    company_id=company_id,
                    economic_customer_number=economic_customer_number,
                    name=name,
                    address=address,
                    postal_code=postal_code,
                    city=city,
                    cvr_number=cvr_number,
                    email=email,
                    phone=phone,
                )
            )
        except ValueError as exc:
            errors.append(f"Linje {file_line}: {exc}")

    if errors:
        return [], errors
    return rows, []
