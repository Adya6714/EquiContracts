"""GECPL end-to-end chain: inbound → Intake → follow-up → Extraction (live models)."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import text

from ..core.db import AdminSessionFactory, org_scoped_session
from ..core.storage import DocumentStorage
from ..services import inbound as inbound_service
from .agent_events import run_once

ROOT = Path(__file__).resolve().parents[4]
EVAL_ROOT = ROOT / "eval" / "eval_set_v0"
REFERENCE_DOCS = ROOT / "Equicontracts Reference Documents"
GECPL_REF = (
    "sample - BG related resolution statement -GECPL BG invocation "
    "5-7-22- ( Final draft).msg"
)


def _resolve_gecpl() -> Path:
    staged = EVAL_ROOT / "documents" / "gecpl-bg-invocation.msg"
    if staged.exists() and staged.stat().st_size > 0:
        return staged
    candidate = REFERENCE_DOCS / GECPL_REF
    if candidate.exists():
        return candidate
    raise FileNotFoundError("no local GECPL document for eval-chain")


def _seed_engagement() -> tuple[UUID, UUID, UUID]:
    """Return (contractor_org_id, engagement_id, client_org_id)."""

    client_id = uuid4()
    contractor_id = uuid4()
    eng_id = uuid4()
    site_id = uuid4()
    suffix = uuid4().hex[:8]
    admin = AdminSessionFactory()
    try:
        admin.execute(
            text(
                """
                INSERT INTO org (id, name, org_type) VALUES
                  (:client, :cname, 'client'),
                  (:contractor, :rname, 'contractor')
                """
            ),
            {
                "client": client_id,
                "cname": f"Eval Client {suffix}",
                "contractor": contractor_id,
                "rname": f"Eval Contractor {suffix}",
            },
        )
        admin.execute(
            text(
                """
                INSERT INTO site (id, owner_org_id, name, city)
                VALUES (:site, :client, 'Eval Site', 'Mumbai')
                """
            ),
            {"site": site_id, "client": client_id},
        )
        admin.execute(
            text(
                """
                INSERT INTO engagement (
                  id, owner_org_id, site_id, name, project_code, inbound_alias
                ) VALUES (
                  :eng, :contractor, :site, 'Eval Engagement',
                  :code, :alias
                )
                """
            ),
            {
                "eng": eng_id,
                "contractor": contractor_id,
                "site": site_id,
                "code": f"EC-EVL-{suffix[:3].upper()}",
                "alias": f"ecevl{suffix[:6]}",
            },
        )
        admin.commit()
    finally:
        admin.close()
    return contractor_id, eng_id, client_id


def _print_trace(*, org_id: UUID, engagement_id: UUID) -> None:
    admin = AdminSessionFactory()
    try:
        events = (
            admin.execute(
                text(
                    """
                    SELECT id, event_type, caused_by_event_id, chain_depth, status,
                           idempotency_key, payload
                    FROM event
                    WHERE org_id = :org AND engagement_id = :eng
                    ORDER BY created_at, chain_depth
                    """
                ),
                {"org": org_id, "eng": engagement_id},
            )
            .mappings()
            .all()
        )
        print("=== Events ===")
        for row in events:
            print(
                f"event {row['id']} type={row['event_type']} "
                f"cause={row['caused_by_event_id']} depth={row['chain_depth']} "
                f"status={row['status']} key={row['idempotency_key']} "
                f"payload={json.dumps(row['payload'], default=str)}"
            )

        runs = (
            admin.execute(
                text(
                    """
                    SELECT id, event_id, agent_name, status, model_version, cost,
                           steps_used
                    FROM agent_run
                    WHERE org_id = :org
                    ORDER BY started_at
                    """
                ),
                {"org": org_id},
            )
            .mappings()
            .all()
        )
        print("=== Runs ===")
        for row in runs:
            print(
                f"run {row['id']} event={row['event_id']} agent={row['agent_name']} "
                f"status={row['status']} model={row['model_version']} "
                f"cost={row['cost']} steps={row['steps_used']}"
            )

        proposals = (
            admin.execute(
                text(
                    """
                    SELECT id, run_id, proposal_type, content, confidence,
                           autonomy_level, state
                    FROM agent_proposal
                    WHERE org_id = :org
                    ORDER BY created_at
                    """
                ),
                {"org": org_id},
            )
            .mappings()
            .all()
        )
        print("=== Proposals ===")
        for row in proposals:
            content = row["content"] or {}
            keys = {}
            if isinstance(content, dict):
                for key in (
                    "document_id",
                    "doc_type",
                    "evidence_weight",
                    "field_name",
                    "value",
                    "reason",
                    "reason_code",
                    "dispute_signals",
                ):
                    if key in content:
                        keys[key] = content[key]
            print(
                f"proposal {row['id']} run={row['run_id']} "
                f"type={row['proposal_type']} autonomy={row['autonomy_level']} "
                f"conf={row['confidence']} state={row['state']} "
                f"content={json.dumps(keys, default=str)}"
            )
    finally:
        admin.close()


def _cleanup(*, org_id: UUID, engagement_id: UUID, client_id: UUID) -> None:
    admin = AdminSessionFactory()
    try:
        admin.execute(
            text("DELETE FROM review_decision WHERE org_id = :org"),
            {"org": org_id},
        )
        admin.execute(
            text("DELETE FROM agent_proposal WHERE org_id = :org"),
            {"org": org_id},
        )
        admin.execute(
            text("DELETE FROM agent_step WHERE org_id = :org"),
            {"org": org_id},
        )
        admin.execute(
            text("DELETE FROM agent_run WHERE org_id = :org"),
            {"org": org_id},
        )
        admin.execute(
            text("DELETE FROM event WHERE org_id = :org"),
            {"org": org_id},
        )
        admin.execute(
            text(
                """
                DELETE FROM extracted_field
                WHERE document_id IN (
                  SELECT id FROM document WHERE engagement_id = :eng
                )
                """
            ),
            {"eng": engagement_id},
        )
        admin.execute(
            text("DELETE FROM document WHERE engagement_id = :eng"),
            {"eng": engagement_id},
        )
        admin.execute(
            text("DELETE FROM engagement WHERE id = :eng"),
            {"eng": engagement_id},
        )
        admin.execute(
            text("DELETE FROM site WHERE owner_org_id = :client"),
            {"client": client_id},
        )
        admin.execute(
            text("DELETE FROM org WHERE id IN (:org, :client)"),
            {"org": org_id, "client": client_id},
        )
        admin.commit()
    finally:
        admin.close()


class _NoSseClient:
    """MinIO local often rejects SSE; strip encryption kwargs for eval only."""

    def __init__(self, inner: object) -> None:
        self._inner = inner

    def put_object(self, **kwargs: object) -> object:
        clean = {k: v for k, v in kwargs.items() if k != "ServerSideEncryption"}
        return self._inner.put_object(**clean)  # type: ignore[attr-defined]

    def get_object(self, **kwargs: object) -> object:
        return self._inner.get_object(**kwargs)  # type: ignore[attr-defined]

    def generate_presigned_url(self, *args: object, **kwargs: object) -> str:
        result = self._inner.generate_presigned_url(  # type: ignore[attr-defined]
            *args, **kwargs
        )
        return str(result)


def main() -> int:
    path = _resolve_gecpl()
    body = path.read_bytes()

    org_id, eng_id, client_id = _seed_engagement()
    print("=== Eval chain (GECPL, live models) ===")
    print(f"document: {path}")
    print(f"org_id={org_id} engagement_id={eng_id}")

    base = DocumentStorage()
    storage = DocumentStorage(client=_NoSseClient(base.client))

    try:
        with org_scoped_session(org_id) as session:
            stored = storage.put_document(body)
            doc_id = inbound_service.accept_document(
                session,
                org_id=org_id,
                project_id=eng_id,
                filename=path.name,
                storage_uri=stored.uri,
                sha256=stored.sha256,
                sender_email=None,
                subject="GECPL BG eval chain",
            )
            print(f"accepted document_id={doc_id}")

        for _ in range(10):
            if not run_once():
                break

        _print_trace(org_id=org_id, engagement_id=eng_id)
    finally:
        _cleanup(org_id=org_id, engagement_id=eng_id, client_id=client_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
