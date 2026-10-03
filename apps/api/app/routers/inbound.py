"""HMAC-authenticated inbound email webhook."""

import base64
import binascii
import hashlib
import hmac
import re
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.db import org_scoped_session, privileged_session
from ..core.storage import DocumentStorage

router = APIRouter(prefix="/inbound", tags=["inbound"])

REMINDER_PATTERN = re.compile(r"\breminder\s*[-:#]?\s*(\d+)\b", re.IGNORECASE)


class InboundEmail(BaseModel):
    recipient: str = Field(min_length=3, max_length=320)
    sender: str | None = Field(default=None, max_length=320)
    subject: str = Field(default="", max_length=998)
    filename: str = Field(min_length=1, max_length=255)
    content_base64: str


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


def _verify_signature(raw_body: bytes, supplied_signature: str) -> None:
    expected = hmac.new(
        get_settings().inbound_email_hmac_secret.encode(),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, supplied_signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"detail": "invalid webhook signature", "code": "invalid_signature"},
        )


def _resolve_project(session: Session, recipient: str) -> dict[str, Any] | None:
    alias = extract_inbound_alias(recipient)
    if alias is None:
        return None
    row = (
        session.execute(
            text(
                """
                SELECT id, owner_org_id
                FROM resolve_inbound_project(:alias)
                """
            ),
            {"alias": alias},
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row is not None else None


def _quarantine(session: Session, recipient: str, payload_hash: str) -> None:
    session.execute(
        text(
            """
            SELECT quarantine_inbound(
              :recipient, :payload_hash, 'unknown_recipient'
            )
            """
        ),
        {
            "recipient": recipient,
            "payload_hash": payload_hash,
        },
    )


@router.post("/email", status_code=status.HTTP_202_ACCEPTED)
async def receive_email(
    request: Request,
    x_inbound_signature: Annotated[str, Header()],
) -> dict[str, str]:
    raw_body = await request.body()
    _verify_signature(raw_body, x_inbound_signature)

    try:
        payload = InboundEmail.model_validate_json(raw_body)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"detail": "invalid inbound payload", "code": "invalid_payload"},
        ) from exc

    payload_hash = hashlib.sha256(raw_body).hexdigest()
    with privileged_session() as session:
        project = _resolve_project(session, payload.recipient)
        if project is None:
            _quarantine(session, payload.recipient, payload_hash)
            return {"status": "quarantined"}

    try:
        content = base64.b64decode(payload.content_base64, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "detail": "invalid attachment encoding",
                "code": "invalid_attachment",
            },
        ) from exc

    owner_org_id = UUID(str(project["owner_org_id"]))
    stored = DocumentStorage().put_document(content)
    with org_scoped_session(owner_org_id) as session:
        document_id = session.execute(
            text(
                """
                INSERT INTO document (
                  project_id, filename, storage_uri, sha256, source,
                  sender_email, reminder_sequence_number
                )
                VALUES (
                  :project_id, :filename, :storage_uri, :sha256,
                  'email_forward', :sender_email, :reminder_sequence_number
                )
                ON CONFLICT (project_id, sha256)
                DO UPDATE SET received_at = EXCLUDED.received_at
                RETURNING id
                """
            ),
            {
                "project_id": project["id"],
                "filename": payload.filename,
                "storage_uri": stored.uri,
                "sha256": stored.sha256,
                "sender_email": payload.sender,
                "reminder_sequence_number": parse_reminder_sequence(payload.subject),
            },
        ).scalar_one()

    return {"status": "accepted", "document_id": str(document_id)}
