"""InvoiceDocumentClassifier — stub implementation.

Classifies whether a mail/document is payment-relevant.
Real implementation would use a local LLM. This stub uses keyword heuristics
so tests and dev ingestion work without any AI infrastructure.
"""
from __future__ import annotations

from dataclasses import dataclass

_NOT_RELEVANT_KEYWORDS = {
    "ikke relevant", "nyhedsbrev", "newsletter", "reklame", "tilbud",
    "invitation", "no-reply", "unsubscribe", "afmeld",
}

_INVOICE_KEYWORDS = {
    "faktura", "invoice", "regning", "betalingspåmindelse", "rykker",
    "kreditnota", "kvittering", "betalingsadvis", "forfaldsdato",
    "due date", "payment due", "please pay", "bedes betale",
}

_REMINDER_KEYWORDS = {
    "rykker", "påmindelse", "reminder", "overdue", "forfalden",
    "rykker 1", "rykker 2", "1. rykker", "2. rykker",
}


@dataclass
class ClassificationResult:
    document_type: str  # invoice | reminder | credit_note | receipt | payment_notice | unknown
    is_payment_relevant: bool
    confidence: float
    reason: str


def classify(
    subject: str,
    body_text: str,
    filename: str = "",
) -> ClassificationResult:
    """Stub classifier using keyword heuristics."""
    text = f"{subject} {body_text} {filename}".lower()

    for kw in _NOT_RELEVANT_KEYWORDS:
        if kw in text:
            return ClassificationResult(
                document_type="unknown",
                is_payment_relevant=False,
                confidence=0.9,
                reason=f"not_relevant_keyword:{kw}",
            )

    is_reminder = any(kw in text for kw in _REMINDER_KEYWORDS)
    is_invoice = any(kw in text for kw in _INVOICE_KEYWORDS)

    if is_reminder:
        return ClassificationResult(
            document_type="reminder",
            is_payment_relevant=True,
            confidence=0.85,
            reason="reminder_keyword",
        )
    if is_invoice:
        return ClassificationResult(
            document_type="invoice",
            is_payment_relevant=True,
            confidence=0.85,
            reason="invoice_keyword",
        )

    return ClassificationResult(
        document_type="unknown",
        is_payment_relevant=False,
        confidence=0.5,
        reason="no_relevant_keywords",
    )
