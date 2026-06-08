"""Generate a PDF for a Quote."""
from __future__ import annotations
import io
from datetime import date

from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable,
)

from .builder import (
    ACCENT, CONTENT_W, DARK, LIGHT_GRAY, MARGIN, MID_GRAY, PAGE_H, PAGE_W,
    WHITE, build_styles, get_font,
)


def _fmt_date(d: date | str | None) -> str:
    if d is None:
        return "—"
    if isinstance(d, str):
        return d
    return d.strftime("%d.%m.%Y")


def _fmt_money(v: float) -> str:
    return f"{v:,.2f} kr.".replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_qty(v: float) -> str:
    if v == int(v):
        return str(int(v))
    return f"{v:g}"


def generate_quote_pdf(
    *,
    quote_number: str,
    title: str,
    valid_until,
    notes: str | None,
    company_name: str,
    company_address: str | None,
    company_cvr_masked: str | None,
    customer_name: str,
    customer_address: str | None,
    project_title: str,
    subtotal: float,
    vat_amount: float,
    total: float,
    lines: list[dict],
) -> bytes:
    buf = io.BytesIO()
    font = get_font()
    styles = build_styles(font)

    doc = SimpleDocTemplate(
        buf,
        pagesize=(PAGE_W, PAGE_H),
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
    )

    story = []

    # ── Header ────────────────────────────────────────────────────────────────
    company_lines = [company_name]
    if company_address:
        company_lines.append(company_address)
    if company_cvr_masked:
        company_lines.append(f"CVR: {company_cvr_masked}")

    valid_str = _fmt_date(valid_until) if valid_until else "Ikke angivet"
    meta_text = (
        f"<b>TILBUD</b><br/>"
        f"{quote_number}<br/>"
        f"Gyldigt til: {valid_str}"
    )

    header_data = [
        [Paragraph("<br/>".join(company_lines), styles["normal"]),
         Paragraph(meta_text, styles["right"])],
    ]
    header_table = Table(header_data, colWidths=[CONTENT_W * 0.55, CONTENT_W * 0.45])
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 6 * mm))

    # ── Title ─────────────────────────────────────────────────────────────────
    story.append(Paragraph(title, styles["h1"]))
    story.append(HRFlowable(width=CONTENT_W, thickness=1, color=ACCENT))
    story.append(Spacer(1, 4 * mm))

    # ── Customer + project ────────────────────────────────────────────────────
    left_col = [f"<b>Tilbud til</b>", customer_name]
    if customer_address:
        left_col.append(customer_address)
    right_col = [f"<b>Sag</b>", project_title]

    addr_data = [[
        Paragraph("<br/>".join(left_col), styles["normal"]),
        Paragraph("<br/>".join(right_col), styles["normal"]),
    ]]
    addr_table = Table(addr_data, colWidths=[CONTENT_W * 0.5, CONTENT_W * 0.5])
    addr_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(addr_table)
    story.append(Spacer(1, 6 * mm))

    # ── Line items ────────────────────────────────────────────────────────────
    col_desc = CONTENT_W * 0.45
    col_unit = CONTENT_W * 0.12
    col_qty = CONTENT_W * 0.10
    col_price = CONTENT_W * 0.165
    col_total = CONTENT_W * 0.165

    thead = [
        Paragraph("Beskrivelse", styles["bold"]),
        Paragraph("Enhed", styles["bold"]),
        Paragraph("Antal", styles["bold_right"]),
        Paragraph("Enhedspris", styles["bold_right"]),
        Paragraph("Beløb", styles["bold_right"]),
    ]
    table_data = [thead]
    for ln in lines:
        row = [
            Paragraph(ln.get("description", ""), styles["normal"]),
            Paragraph(ln.get("unit") or "", styles["small"]),
            Paragraph(_fmt_qty(ln.get("quantity", 0)), styles["right"]),
            Paragraph(_fmt_money(ln.get("unit_price", 0)), styles["right"]),
            Paragraph(_fmt_money(ln.get("line_total", 0)), styles["right"]),
        ]
        table_data.append(row)

    lines_table = Table(
        table_data,
        colWidths=[col_desc, col_unit, col_qty, col_price, col_total],
        repeatRows=1,
    )
    lines_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_GRAY]),
        ("GRID", (0, 0), (-1, -1), 0.25, MID_GRAY),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(lines_table)
    story.append(Spacer(1, 4 * mm))

    # ── Totals ────────────────────────────────────────────────────────────────
    totals_data = [
        [Paragraph("Subtotal ekskl. moms", styles["right"]),
         Paragraph(_fmt_money(subtotal), styles["right"])],
        [Paragraph("Moms 25%", styles["right"]),
         Paragraph(_fmt_money(vat_amount), styles["right"])],
        [Paragraph("<b>Total inkl. moms</b>", styles["total"]),
         Paragraph(f"<b>{_fmt_money(total)}</b>", styles["total"])],
    ]
    totals_table = Table(
        totals_data,
        colWidths=[CONTENT_W * 0.75, CONTENT_W * 0.25],
    )
    totals_table.setStyle(TableStyle([
        ("LINEABOVE", (0, 2), (-1, 2), 1, ACCENT),
        ("TOPPADDING", (0, 2), (-1, 2), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(totals_table)

    # ── Notes ─────────────────────────────────────────────────────────────────
    if notes:
        story.append(Spacer(1, 6 * mm))
        story.append(HRFlowable(width=CONTENT_W, thickness=0.5, color=MID_GRAY))
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph("<b>Bemærkninger</b>", styles["h2"]))
        story.append(Paragraph(notes, styles["normal"]))

    doc.build(story)
    return buf.getvalue()
