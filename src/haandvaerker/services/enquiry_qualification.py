"""Qualification checklist policy for Enquiry → Project conversion.

Policy lives here, not in the transport layer (vision §7, AGENTS rule 8).
The convert handler and the qualification-status endpoint both call
``check_qualification`` — one shared policy function, no parallel checks.
"""
from dataclasses import dataclass
from ..models.enquiry import Enquiry


@dataclass
class QualificationResult:
    ready: bool
    checklist: list[dict]
    missing_fields: list[str]


_GATES: list[tuple[str, str, str]] = [
    # (field_name, label, missing_message)
    ("contact_name", "Kontaktnavn udfyldt", "contact_name"),
    ("notes", "Opgavebeskrivelse udfyldt (notes)", "notes"),
    ("address", "Adresse udfyldt", "address"),
    ("work_type", "Arbejdstype udfyldt", "work_type"),
]

_CONTACT_GATE_LABEL = "Kontaktinfo: e-mail eller telefon udfyldt"
_CONTACT_MISSING = "contact_email_or_phone"


def check_qualification(enquiry: Enquiry) -> QualificationResult:
    """Return a QualificationResult for *enquiry*.

    The 5 gates are:
    1. contact_name non-null
    2. contact_email OR contact_phone non-null
    3. notes non-null
    4. address non-null
    5. work_type non-null

    All 5 must pass for ``ready`` to be ``True``.
    """
    checklist: list[dict] = []
    missing_fields: list[str] = []

    for attr, label, missing_key in _GATES:
        passed = getattr(enquiry, attr) is not None
        checklist.append({"gate": label, "passed": passed})
        if not passed:
            missing_fields.append(missing_key)

    # Gate 2: contact_email OR contact_phone
    contact_ok = bool(enquiry.contact_email) or bool(enquiry.contact_phone)
    checklist.insert(1, {"gate": _CONTACT_GATE_LABEL, "passed": contact_ok})
    if not contact_ok:
        missing_fields.append(_CONTACT_MISSING)

    ready = len(missing_fields) == 0
    return QualificationResult(ready=ready, checklist=checklist, missing_fields=missing_fields)
