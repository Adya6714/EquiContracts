"""HMAC-authenticated inbound email webhook."""

import base64
import binascii
import hashlib
import hmac
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, Field, ValidationError

from ..core.config import get_settings
from ..core.db import org_scoped_session, privileged_session
from ..core.storage import DocumentStorage
from ..services import inbound as inbound_service
from ..services.inbound import extract_inbound_alias, parse_reminder_sequence

router = APIRouter(prefix="/inbound", tags=["inbound"])

# Re-export for existing unit tests (import path unchanged).
__all__ = [
    "router",
    "InboundEmail",
    "extract_inbound_alias",
    "parse_reminder_sequence",
    "receive_email",
]


class InboundEmail(BaseModel):
    recipient: str = Field(min_length=3, max_length=320)
    sender: str | None = Field(default=None, max_length=320)
    subject: str = Field(default="", max_length=998)
    filename: str = Field(min_length=1, max_length=255)
    content_base64: str


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
        project = inbound_service.resolve_project_or_quarantine(
            session,
            recipient=payload.recipient,
            payload_hash=payload_hash,
        )
        if project is None:
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
        document_id = inbound_service.accept_document(
            session,
            project_id=UUID(str(project["id"])),
            filename=payload.filename,
            storage_uri=stored.uri,
            sha256=stored.sha256,
            sender_email=payload.sender,
            subject=payload.subject,
        )

    return {"status": "accepted", "document_id": str(document_id)}
