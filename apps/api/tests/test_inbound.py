import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from apps.api.app.core.config import get_settings
from apps.api.app.main import app
from apps.api.app.routers.inbound import (
    extract_inbound_alias,
    parse_reminder_sequence,
)

client = TestClient(app)


def _sign(body: bytes) -> str:
    return hmac.new(
        get_settings().inbound_email_hmac_secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()


def test_parses_reminder_sequence() -> None:
    assert parse_reminder_sequence("Reminder - 02: payment overdue") == 2


def test_subject_without_reminder_has_no_sequence() -> None:
    assert parse_reminder_sequence("Submission of RA Bill 04") is None


def test_extract_inbound_alias_from_plus_address() -> None:
    assert extract_inbound_alias("projects+ecmum101@equicontracts.in") == "ecmum101"


def test_extract_inbound_alias_requires_plus() -> None:
    assert extract_inbound_alias("projects@equicontracts.in") is None


def test_invalid_signature_is_rejected_before_database_access() -> None:
    response = client.post(
        "/inbound/email",
        content=b"{}",
        headers={"x-inbound-signature": "invalid"},
    )
    assert response.status_code == 401


def test_recipient_without_plus_is_quarantined() -> None:
    body = json.dumps(
        {
            "recipient": "projects@equicontracts.in",
            "subject": "no alias",
            "filename": "note.pdf",
            "content_base64": "cQ==",
        }
    ).encode()
    mock_session = MagicMock()
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_session
    mock_cm.__exit__.return_value = None

    with patch(
        "apps.api.app.routers.inbound.privileged_session",
        return_value=mock_cm,
    ):
        response = client.post(
            "/inbound/email",
            content=body,
            headers={"x-inbound-signature": _sign(body)},
        )

    assert response.status_code == 202
    assert response.json() == {"status": "quarantined"}
    assert mock_session.execute.call_count == 1
    sql = str(mock_session.execute.call_args.args[0])
    assert "quarantine_inbound" in sql
