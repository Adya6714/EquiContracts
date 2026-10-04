"""Opaque services handle passed into packages.agents.RunContext."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from ..services import agent_events as agent_events_service
from ..services import agent_reads as agent_reads_service


class WorkerServiceHandle:
    """Session-bound callbacks for tools and the runtime. Not a DB session."""

    def __init__(
        self,
        session: Session,
        *,
        pinned_document_id: UUID | None = None,
        storage: Any | None = None,
    ) -> None:
        self._session = session
        self.pinned_document_id = pinned_document_id
        self._storage = storage

    def fetch_engagement_context(self, *, engagement_id: UUID) -> dict[str, Any] | None:
        return agent_reads_service.get_engagement_context(
            self._session, engagement_id=engagement_id
        )

    def fetch_document_metadata(self, *, document_id: UUID) -> dict[str, Any] | None:
        return agent_reads_service.get_document_metadata(
            self._session, document_id=document_id
        )

    def fetch_document_pages(self, *, document_id: UUID) -> dict[str, Any] | None:
        return agent_reads_service.get_document_pages(
            self._session,
            document_id=document_id,
            storage=self._storage,
        )

    def record_step(
        self,
        *,
        run_id: UUID,
        org_id: UUID,
        step_no: int,
        outcome: str,
        tool_called: str | None = None,
        input_payload: dict[str, Any] | None = None,
        output_payload: dict[str, Any] | None = None,
    ) -> UUID:
        return agent_events_service.record_step(
            self._session,
            run_id=run_id,
            org_id=org_id,
            step_no=step_no,
            outcome=outcome,
            tool_called=tool_called,
            input_payload=input_payload,
            output_payload=output_payload,
        )

    def create_proposal(
        self,
        *,
        run_id: UUID,
        org_id: UUID,
        proposal_type: str,
        content: dict[str, Any],
        autonomy_level: int,
        engagement_id: UUID | None = None,
        confidence: Decimal | None = None,
    ) -> UUID:
        return agent_events_service.create_proposal(
            self._session,
            run_id=run_id,
            org_id=org_id,
            engagement_id=engagement_id,
            proposal_type=proposal_type,
            content=content,
            autonomy_level=autonomy_level,
            confidence=confidence,
        )
