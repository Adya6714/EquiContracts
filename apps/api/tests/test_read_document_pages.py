"""read_document_pages tool + get_document_bytes (no network)."""

from __future__ import annotations

import json
from io import BytesIO
from uuid import uuid4

import pytest
from sqlalchemy import text

from apps.api.app.core.db import (
    AdminSessionFactory,
    agent_org_scoped_session,
    org_scoped_session,
)
from apps.api.app.core.storage import DocumentStorage
from apps.api.app.services import agent_events as agent_events_service
from apps.api.app.workers.service_handle import WorkerServiceHandle
from packages.agents.context import RunContext
from packages.agents.runtime import AgentRuntime, sanitize_for_log
from packages.agents.tools._base import ToolRefusal
from packages.agents.tools.read_document_pages import run as read_pages


class FakeS3:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.put: dict[str, object] | None = None

    def put_object(self, **kwargs: object) -> None:
        self.put = kwargs
        key = str(kwargs["Key"])
        body = kwargs["Body"]
        self.objects[key] = body if isinstance(body, bytes) else bytes(body)  # type: ignore[arg-type]

    def get_object(self, **kwargs: object) -> dict[str, object]:
        key = str(kwargs["Key"])
        return {"Body": BytesIO(self.objects[key])}

    def generate_presigned_url(
        self, operation: str, *, Params: dict, ExpiresIn: int
    ) -> str:
        return f"https://signed.invalid/{operation}/{Params['Key']}?ttl={ExpiresIn}"


def test_get_document_bytes_round_trip_and_refuses_paths() -> None:
    fake = FakeS3()
    storage = DocumentStorage(client=fake)
    stored = storage.put_document(b"hello bg text")
    assert storage.get_document_bytes(stored.uri) == b"hello bg text"

    with pytest.raises(ValueError, match="s3://"):
        storage.get_document_bytes("/tmp/secret.pdf")
    with pytest.raises(ValueError, match="s3://"):
        storage.get_document_bytes("file:///tmp/secret.pdf")
    with pytest.raises(ValueError, match="outside"):
        storage.get_document_bytes("s3://other-bucket/sha256/ab/cd")


def test_read_document_pages_same_engagement_and_step_log(
    access_data,
) -> None:
    fake = FakeS3()
    storage = DocumentStorage(client=fake)
    body = b"Bank guarantee text for page load test."
    stored = storage.put_document(body)
    doc_id = uuid4()

    with org_scoped_session(access_data.contractor_a) as session:
        session.execute(
            text(
                """
                INSERT INTO document (
                  id, engagement_id, filename, storage_uri, sha256, source
                ) VALUES (
                  :id, :engagement_id, 'bg.txt', :uri, :sha, 'manual_upload'
                )
                """
            ),
            {
                "id": doc_id,
                "engagement_id": access_data.project_a,
                "uri": stored.uri,
                "sha": stored.sha256,
            },
        )
        event = agent_events_service.create_event(
            session,
            org_id=access_data.contractor_a,
            event_type="test.echo",
            idempotency_key=f"pages-{uuid4().hex}",
            engagement_id=access_data.project_a,
        )
        event_id = event["id"]

    with agent_org_scoped_session(access_data.contractor_a) as session:
        run = agent_events_service.start_run(
            session,
            event_id=event_id,
            org_id=access_data.contractor_a,
            agent_name="extraction",
            agent_version="0",
            engagement_id=access_data.project_a,
            attempt=1,
        )
        handle = WorkerServiceHandle(
            session, pinned_document_id=doc_id, storage=storage
        )
        ctx = RunContext(
            org_id=access_data.contractor_a,
            engagement_id=access_data.project_a,
            run_id=run.run_id,
            services=handle,
        )
        runtime = AgentRuntime(context=ctx, agent_name="extraction")
        result = runtime.call_tool("read_document_pages", document_id=doc_id)

        assert result["document_id"] == str(doc_id)
        assert result["page_count"] == 1
        assert result["pages"][0]["page"] is None
        assert "Bank guarantee text" in result["pages"][0]["text"]

        steps = (
            session.execute(
                text(
                    """
                SELECT input, output FROM agent_step
                WHERE run_id = :run_id
                ORDER BY step_no
                """
                ),
                {"run_id": run.run_id},
            )
            .mappings()
            .all()
        )
        assert len(steps) == 1
        logged = json.dumps({"in": steps[0]["input"], "out": steps[0]["output"]})
        assert "Bank guarantee text" not in logged
        assert "page load test" not in logged
        assert steps[0]["output"].get("document_id") == str(doc_id)
        assert steps[0]["output"].get("page_count") == 1
        assert "pages" not in steps[0]["output"]


def test_read_document_pages_refuses_other_engagement_org_and_non_pinned(
    access_data,
) -> None:
    fake = FakeS3()
    storage = DocumentStorage(client=fake)
    stored = storage.put_document(b"secret other doc")
    other_engagement = uuid4()
    other_doc = uuid4()
    foreign_doc = uuid4()
    pinned = access_data.document_a

    admin = AdminSessionFactory()
    try:
        admin.execute(
            text(
                """
                INSERT INTO engagement (
                  id, owner_org_id, name, project_code, inbound_alias
                ) VALUES (
                  :id, :org, 'Other Eng', :code, :alias
                )
                """
            ),
            {
                "id": other_engagement,
                "org": access_data.contractor_a,
                "code": f"EC-O-{uuid4().hex[:6]}",
                "alias": f"eco{uuid4().hex[:8]}",
            },
        )
        admin.execute(
            text(
                """
                INSERT INTO document (
                  id, engagement_id, filename, storage_uri, sha256, source
                ) VALUES
                  (
                    :other_doc, :other_engagement, 'x.txt', :uri, :sha,
                    'manual_upload'
                  ),
                  (
                    :foreign_doc, :project_b, 'y.txt', :uri, :sha2,
                    'manual_upload'
                  )
                """
            ),
            {
                "other_doc": other_doc,
                "other_engagement": other_engagement,
                "foreign_doc": foreign_doc,
                "project_b": access_data.project_b,
                "uri": stored.uri,
                "sha": stored.sha256,
                "sha2": "b" * 64,
            },
        )
        admin.commit()
    finally:
        admin.close()

    with org_scoped_session(access_data.contractor_a) as session:
        handle = WorkerServiceHandle(
            session, pinned_document_id=pinned, storage=storage
        )
        ctx = RunContext(
            org_id=access_data.contractor_a,
            engagement_id=access_data.project_a,
            run_id=uuid4(),
            services=handle,
        )

        with pytest.raises(ToolRefusal) as non_pinned:
            read_pages(ctx, document_id=other_doc)
        assert non_pinned.value.code == "not_pinned_document"

        handle.pinned_document_id = other_doc
        with pytest.raises(ToolRefusal) as wrong_eng:
            read_pages(ctx, document_id=other_doc)
        assert wrong_eng.value.code == "wrong_engagement"

        handle.pinned_document_id = foreign_doc
        with pytest.raises(ToolRefusal) as foreign:
            read_pages(ctx, document_id=foreign_doc)
        assert foreign.value.code in {"document_not_found", "wrong_engagement"}

    admin = AdminSessionFactory()
    try:
        admin.execute(
            text("DELETE FROM document WHERE id IN (:a, :b)"),
            {"a": other_doc, "b": foreign_doc},
        )
        admin.execute(
            text("DELETE FROM engagement WHERE id = :id"),
            {"id": other_engagement},
        )
        admin.commit()
    finally:
        admin.close()


def test_sanitize_keeps_token_counts_not_page_text() -> None:
    clean = sanitize_for_log(
        {
            "document_id": "11111111-1111-1111-1111-111111111111",
            "page_count": 3,
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "pages": [{"page": 1, "text": "SECRET PAGE BODY"}],
            "text": "SECRET PAGE BODY",
        }
    )
    assert clean["page_count"] == 3
    assert clean["prompt_tokens"] == 100
    assert clean["completion_tokens"] == 50
    assert "pages" not in clean
    assert "text" not in clean
    blob = json.dumps(clean)
    assert "SECRET" not in blob
