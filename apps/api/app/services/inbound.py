"""Business logic for inbound email acceptance."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from ..repositories import inbound as inbound_repo

REMINDER_PATTERN = re.compile(r"\breminder\s*[-:#]?\s*(\d+)\b", re.IGNORECASE)


def parse_reminder_sequence(subject: str) -> int | None:
    match = REMINDER_PATTERN.search(subject)
    return int(match.group(1)) if match else None


def extract_inbound_alias(recipient: str) -> str | None:
    """Parse projects+{alias}@domain → alias. No '+' means unmatched."""
    address = recipient.strip()
    if "<" in address and ">" in address:
        address = address[address.rfind("<") + 1 : address.rfind(">")].strip()
    if "@" not in address:
        return None
    local_part, _, _domain = address.partition("@")
    if "+" not in local_part:
        return None
    _mailbox, alias = local_part.split("+", 1)
    alias = alias.strip().lower()
    return alias or None


def resolve_project_or_quarantine(
    session: Session,
    *,
    recipient: str,
    payload_hash: str,
) -> dict[str, Any] | None:
    """Resolve via system-role session, or quarantine. Returns project row or None."""

    alias = extract_inbound_alias(recipient)
    if alias is None:
        inbound_repo.quarantine_unknown_recipient(
            session, recipient=recipient, payload_hash=payload_hash
        )
        return None
    project = inbound_repo.resolve_project_by_alias(session, alias=alias)
    if project is None:
        inbound_repo.quarantine_unknown_recipient(
            session, recipient=recipient, payload_hash=payload_hash
        )
        return None
    return project


def accept_document(
    session: Session,
    *,
    project_id: UUID,
    filename: str,
    storage_uri: str,
    sha256: str,
    sender_email: str | None,
    subject: str,
) -> UUID:
    return inbound_repo.upsert_inbound_document(
        session,
        project_id=project_id,
        filename=filename,
        storage_uri=storage_uri,
        sha256=sha256,
        sender_email=sender_email,
        reminder_sequence_number=parse_reminder_sequence(subject),
    )
