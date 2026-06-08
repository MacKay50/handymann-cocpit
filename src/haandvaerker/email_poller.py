"""
IMAP email poller — henter ulæste emails og gemmer dem i Indbakken.

Konfiguration via .env-fil (se .env.example):
  EMAIL_IMAP_HOST     IMAP-serverens hostname
  EMAIL_IMAP_PORT     Port (standard: 993)
  EMAIL_USER          Email-adresse / brugernavn
  EMAIL_PASSWORD      Adgangskode eller App Password
  EMAIL_FOLDER        Mappe at læse fra (standard: INBOX)
"""
from __future__ import annotations

import email
import email.header
import email.utils
import imaplib
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Session, select

from .config import (
    EMAIL_FOLDER,
    EMAIL_IMAP_HOST,
    EMAIL_IMAP_PORT,
    EMAIL_PASSWORD,
    EMAIL_USER,
)
from .models.inbox_message import InboxMessage, InboxSource


class EmailConfigError(Exception):
    pass


def is_configured() -> bool:
    return bool(EMAIL_IMAP_HOST and EMAIL_USER and EMAIL_PASSWORD)


def _decode(value: str) -> str:
    if not value:
        return ""
    parts = []
    for decoded, charset in email.header.decode_header(value):
        if isinstance(decoded, bytes):
            parts.append(decoded.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(str(decoded))
    return "".join(parts).strip()


def _get_body(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition", "")):
                charset = part.get_content_charset() or "utf-8"
                return part.get_payload(decode=True).decode(charset, errors="replace")
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                charset = part.get_content_charset() or "utf-8"
                raw = part.get_payload(decode=True).decode(charset, errors="replace")
                return re.sub(r"<[^>]+>", " ", raw).strip()
        return ""
    charset = msg.get_content_charset() or "utf-8"
    payload = msg.get_payload(decode=True)
    return payload.decode(charset, errors="replace") if payload else ""


def _parse_sender(from_header: str) -> tuple[str, str]:
    name, addr = email.utils.parseaddr(from_header)
    name = _decode(name) if name else (addr.split("@")[0] if addr else "")
    return name, addr.lower()


def _parse_date(date_str: str) -> datetime:
    try:
        parsed = email.utils.parsedate_to_datetime(date_str)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc).replace(tzinfo=None)
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    except Exception:
        return datetime.utcnow()


def poll_inbox(company_id: str, session: Session) -> int:
    """
    Fetch UNSEEN emails from IMAP and insert them into the inbox.
    Marks each email as SEEN after import.
    Returns the number of new messages imported.
    """
    if not is_configured():
        raise EmailConfigError(
            "Email ikke konfigureret. "
            "Udfyld EMAIL_IMAP_HOST, EMAIL_USER og EMAIL_PASSWORD i .env-filen."
        )

    imap = imaplib.IMAP4_SSL(EMAIL_IMAP_HOST, EMAIL_IMAP_PORT)
    try:
        imap.login(EMAIL_USER, EMAIL_PASSWORD)
        imap.select(EMAIL_FOLDER)

        _, data = imap.search(None, "UNSEEN")
        uids = [u for u in data[0].split() if u]
        if not uids:
            return 0

        imported = 0
        for uid in uids:
            try:
                _, msg_data = imap.fetch(uid, "(RFC822)")
                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)

                subject = _decode(msg.get("Subject", "(ingen emne)"))
                sender_name, sender_email = _parse_sender(msg.get("From", ""))
                received_at = _parse_date(msg.get("Date", ""))
                body = _get_body(msg).strip()

                # Dedup: skip if same sender+subject+date already exists
                existing = session.exec(
                    select(InboxMessage)
                    .where(InboxMessage.company_id == company_id)
                    .where(InboxMessage.sender_email == sender_email)
                    .where(InboxMessage.subject == subject)
                ).first()
                if existing:
                    imap.store(uid, "+FLAGS", "\\Seen")
                    continue

                session.add(InboxMessage(
                    id=str(uuid.uuid4()),
                    company_id=company_id,
                    source=InboxSource.email,
                    sender_name=sender_name or None,
                    sender_email=sender_email or None,
                    subject=subject,
                    body=body,
                    received_at=received_at,
                ))
                imap.store(uid, "+FLAGS", "\\Seen")
                imported += 1

            except Exception:
                continue  # skip broken messages, don't abort the whole poll

        session.commit()
        return imported

    finally:
        try:
            imap.close()
            imap.logout()
        except Exception:
            pass
