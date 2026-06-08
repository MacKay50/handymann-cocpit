"""Shared PDF utilities: font registration and colour palette."""
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ── Font registration ─────────────────────────────────────────────────────────

_FONTS_REGISTERED = False


def _ensure_fonts() -> str:
    """Register Arial (Danish-capable) and return the base font name to use."""
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return "Arial"
    try:
        pdfmetrics.registerFont(TTFont("Arial", "C:/Windows/Fonts/arial.ttf"))
        pdfmetrics.registerFont(TTFont("Arial-Bold", "C:/Windows/Fonts/arialbd.ttf"))
        pdfmetrics.registerFontFamily("Arial", normal="Arial", bold="Arial-Bold")
        _FONTS_REGISTERED = True
        return "Arial"
    except Exception:
        return "Helvetica"


# ── Colour palette ────────────────────────────────────────────────────────────

DARK = colors.HexColor("#1a1a2e")
ACCENT = colors.HexColor("#16213e")
LIGHT_GRAY = colors.HexColor("#f5f5f5")
MID_GRAY = colors.HexColor("#cccccc")
WHITE = colors.white

# ── Page constants ────────────────────────────────────────────────────────────

PAGE_W, PAGE_H = A4
MARGIN = 20 * mm
CONTENT_W = PAGE_W - 2 * MARGIN


def get_font() -> str:
    return _ensure_fonts()


def build_styles(font: str) -> dict:
    base = getSampleStyleSheet()
    styles = {
        "h1": ParagraphStyle(
            "h1", fontName=f"{font}-Bold" if font == "Arial" else "Helvetica-Bold",
            fontSize=22, textColor=DARK, spaceAfter=2 * mm,
        ),
        "h2": ParagraphStyle(
            "h2", fontName=f"{font}-Bold" if font == "Arial" else "Helvetica-Bold",
            fontSize=11, textColor=DARK, spaceAfter=1 * mm,
        ),
        "normal": ParagraphStyle(
            "normal", fontName=font, fontSize=9, textColor=DARK,
            leading=13,
        ),
        "small": ParagraphStyle(
            "small", fontName=font, fontSize=8, textColor=colors.HexColor("#555555"),
            leading=11,
        ),
        "right": ParagraphStyle(
            "right", fontName=font, fontSize=9, textColor=DARK,
            alignment=2, leading=13,
        ),
        "bold": ParagraphStyle(
            "bold", fontName=f"{font}-Bold" if font == "Arial" else "Helvetica-Bold",
            fontSize=9, textColor=DARK, leading=13,
        ),
        "bold_right": ParagraphStyle(
            "bold_right", fontName=f"{font}-Bold" if font == "Arial" else "Helvetica-Bold",
            fontSize=9, textColor=DARK, alignment=2, leading=13,
        ),
        "total": ParagraphStyle(
            "total", fontName=f"{font}-Bold" if font == "Arial" else "Helvetica-Bold",
            fontSize=11, textColor=DARK, alignment=2,
        ),
    }
    return styles
