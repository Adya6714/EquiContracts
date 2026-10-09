"""Opaque services handle passed into packages.agents.RunContext."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from ..services import agent_events as agent_events_service
from ..services import agent_reads as agent_reads_service

LlmFn = Callable[..., dict[str, Any]]


class WorkerServiceHandle:
    """Session-bound callbacks for tools and the runtime. Not a DB session."""

    def __init__(
        self,
        session: Session,
        *,
        pinned_document_id: UUID | None = None,
        event_payload: dict[str, Any] | None = None,
        storage: Any | None = None,
        llm_fn: LlmFn | None = None,
    ) -> None:
        self._session = session
        self.pinned_document_id = pinned_document_id
        self.event_payload = event_payload or {}
        self._storage = storage
        self._llm_fn = llm_fn

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

    def call_bg_extraction_llm(self, *, system: str, user: str) -> dict[str, Any]:
        if self._llm_fn is not None:
            return self._llm_fn(system=system, user=user)
        from packages.extraction.bg_extractor import call_extraction_model_detailed
        from packages.extraction.llm_pricing import estimate_would_have_cost

        detailed = call_extraction_model_detailed(system=system, user=user)
        model_version = str(detailed["model_version"])
        prompt_tokens = int(detailed.get("prompt_tokens") or 0)
        completion_tokens = int(detailed.get("completion_tokens") or 0)
        return {
            "model_version": model_version,
            "raw_text": str(detailed["raw_text"]),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cost": str(
                estimate_would_have_cost(
                    model_version,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )
            ),
        }

    def call_intake_llm(self, *, system: str, user: str) -> dict[str, Any]:
        if self._llm_fn is not None:
            return self._llm_fn(system=system, user=user)
        import os

        from packages.extraction.bg_extractor import call_extraction_model_detailed
        from packages.extraction.llm_pricing import estimate_would_have_cost

        # LLM_MODEL_INTAKE overrides LLM_MODEL for this call only.
        intake_model = (os.environ.get("LLM_MODEL_INTAKE") or "").strip()
        previous = os.environ.get("LLM_MODEL")
        if intake_model:
            os.environ["LLM_MODEL"] = intake_model
        try:
            detailed = call_extraction_model_detailed(system=system, user=user)
        finally:
            if intake_model:
                if previous is None:
                    os.environ.pop("LLM_MODEL", None)
                else:
                    os.environ["LLM_MODEL"] = previous

        model_version = str(detailed["model_version"])
        prompt_tokens = int(detailed.get("prompt_tokens") or 0)
        completion_tokens = int(detailed.get("completion_tokens") or 0)
        return {
            "model_version": model_version,
            "raw_text": str(detailed["raw_text"]),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cost": str(
                estimate_would_have_cost(
                    model_version,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )
            ),
        }

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
