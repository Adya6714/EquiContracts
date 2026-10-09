"""Live Intake Agent eval across local eval docs and adversarial fixtures."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from packages.agents.agents.intake import agent as intake_agent
from packages.agents.context import RunContext
from packages.agents.runtime import run_agent
from packages.extraction.document_text import load_document_text, pages_from_text
from packages.extraction.eval_harness import load_cases, resolve_case_document
from packages.extraction.llm_pricing import estimate_would_have_cost

ROOT = Path(__file__).resolve().parents[2]
ADVERSARIAL = ROOT / "eval" / "adversarial"
WEIGHT_LABELS = frozenset({"routine", "core_evidence", "potential_dispute"})
DEFAULT_CHEAP_FLASH = "gemini-2.0-flash"


@dataclass
class _RecordingServices:
    pinned_document_id: Any
    event_payload: dict[str, Any]
    document_text: str
    filename: str = "document.txt"
    steps: list[dict[str, Any]] = field(default_factory=list)
    proposals: list[dict[str, Any]] = field(default_factory=list)
    last_model_version: str = ""
    llm_error: str | None = None

    def fetch_document_metadata(self, *, document_id: Any) -> dict[str, Any]:
        return {
            "id": str(document_id),
            "engagement_id": str(self.event_payload.get("engagement_id") or uuid4()),
            "sha256": "0" * 64,
            "source": "eval",
        }

    def fetch_document_pages(self, *, document_id: Any) -> dict[str, Any]:
        pages = pages_from_text(self.document_text)
        return {
            "document_id": str(document_id),
            "engagement_id": str(self.event_payload.get("engagement_id") or uuid4()),
            "page_count": len(pages),
            "pages": pages,
        }

    def call_intake_llm(self, *, system: str, user: str) -> dict[str, Any]:
        from packages.extraction.bg_extractor import call_extraction_model_detailed

        detailed = call_extraction_model_detailed(system=system, user=user)
        model_version = str(detailed["model_version"])
        prompt_tokens = int(detailed.get("prompt_tokens") or 0)
        completion_tokens = int(detailed.get("completion_tokens") or 0)
        self.last_model_version = model_version
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
        run_id: Any,
        org_id: Any,
        step_no: int,
        outcome: str,
        tool_called: str | None = None,
        input_payload: dict[str, Any] | None = None,
        output_payload: dict[str, Any] | None = None,
    ) -> Any:
        self.steps.append(
            {
                "step_no": step_no,
                "outcome": outcome,
                "tool_called": tool_called,
                "input": input_payload or {},
                "output": output_payload or {},
            }
        )
        return uuid4()

    def create_proposal(
        self,
        *,
        run_id: Any,
        org_id: Any,
        proposal_type: str,
        content: dict[str, Any],
        autonomy_level: int,
        engagement_id: Any = None,
        confidence: Decimal | None = None,
    ) -> Any:
        self.proposals.append(
            {
                "proposal_type": proposal_type,
                "content": content,
                "autonomy_level": autonomy_level,
                "confidence": confidence,
            }
        )
        return uuid4()


def _eval_models() -> list[str]:
    raw = (os.environ.get("INTAKE_EVAL_MODELS") or "").strip()
    if raw:
        models = [m.strip() for m in raw.split(",") if m.strip()]
    else:
        current = (os.environ.get("LLM_MODEL") or "").strip()
        models = [DEFAULT_CHEAP_FLASH]
        if current and current not in models:
            models.append(current)
    # Preserve order, drop empties/dupes
    seen: set[str] = set()
    out: list[str] = []
    for model in models:
        if model not in seen:
            seen.add(model)
            out.append(model)
    return out


def _local_cases() -> list[tuple[str, str, dict[str, Any] | None, Path]]:
    """(case_id, expected_type, case_or_none, path)."""

    rows: list[tuple[str, str, dict[str, Any] | None, Path]] = []
    for case in load_cases():
        try:
            path = resolve_case_document(case)
        except FileNotFoundError:
            print(f"skip {case['id']}: document not available locally")
            continue
        rows.append((case["id"], str(case["doc_type"]), case, path))

    injection = ADVERSARIAL / "injection-bg.txt"
    if injection.is_file():
        rows.append(("adversarial-injection-bg", "bank_guarantee", None, injection))
    return rows


def _expected_weight(case: dict[str, Any] | None) -> str:
    if case is None:
        return "unscored"
    cat = str(case.get("expected_category") or "")
    if cat in WEIGHT_LABELS:
        return cat
    return "unscored"


def _run_one(
    *,
    document_text: str,
    filename: str,
    model: str,
) -> tuple[Any, _RecordingServices]:
    previous_intake = os.environ.get("LLM_MODEL_INTAKE")
    previous_model = os.environ.get("LLM_MODEL")
    os.environ["LLM_MODEL_INTAKE"] = model
    os.environ["LLM_MODEL"] = model
    doc_id = uuid4()
    engagement_id = uuid4()
    services = _RecordingServices(
        pinned_document_id=doc_id,
        event_payload={
            "document_id": str(doc_id),
            "engagement_id": str(engagement_id),
        },
        document_text=document_text,
        filename=filename,
    )
    try:
        ctx = RunContext(
            org_id=uuid4(),
            engagement_id=engagement_id,
            run_id=uuid4(),
            services=services,
        )
        outcome = run_agent(
            ctx,
            agent_name="intake",
            agent_fn=intake_agent.run,
            max_steps=20,
            cost_cap=Decimal("5.00"),
        )
        return outcome, services
    finally:
        if previous_intake is None:
            os.environ.pop("LLM_MODEL_INTAKE", None)
        else:
            os.environ["LLM_MODEL_INTAKE"] = previous_intake
        if previous_model is None:
            os.environ.pop("LLM_MODEL", None)
        else:
            os.environ["LLM_MODEL"] = previous_model


def _classification(services: _RecordingServices) -> dict[str, Any] | None:
    for proposal in services.proposals:
        if proposal["proposal_type"] == "propose_classification":
            content = proposal.get("content") or {}
            if isinstance(content, dict):
                return content
    return None


def _looks_unavailable(msg: str) -> bool:
    return any(
        token in msg
        for token in (
            "notfound",
            "not found",
            "404",
            "unavailable",
            "does not exist",
            "model_not_found",
        )
    )


def main() -> int:
    models = _eval_models()
    cases = _local_cases()
    print("=== Intake eval (live models) ===")
    print(f"models: {', '.join(models)}")
    print(f"cases: {len(cases)}")
    print()

    exit_code = 0
    any_model_ok = False
    for model in models:
        print(f"--- model: {model} ---")
        type_ok = type_total = 0
        weight_ok = weight_total = 0
        dispute_ok = dispute_total = 0
        total_cost = Decimal("0")
        unavailable = False

        for case_id, expected_type, case, path in cases:
            try:
                document_text = load_document_text(path)
            except Exception as exc:
                print(f"{case_id}: skip load error ({type(exc).__name__})")
                continue
            try:
                outcome, services = _run_one(
                    document_text=document_text,
                    filename=path.name,
                    model=model,
                )
            except Exception as exc:
                msg = str(exc).lower()
                if _looks_unavailable(msg):
                    print(f"model {model} unavailable: {type(exc).__name__}: {exc}")
                    unavailable = True
                    exit_code = 1
                    break
                print(f"{case_id}: run error {type(exc).__name__}: {exc}")
                exit_code = 1
                continue

            if outcome.status == "failed" and _looks_unavailable(
                str(outcome.error or "").lower()
            ):
                print(f"model {model} unavailable: run failed with {outcome.error}")
                unavailable = True
                exit_code = 1
                break

            content = _classification(services) or {}
            predicted_type = str(content.get("doc_type") or "")
            predicted_weight = str(content.get("evidence_weight") or "")
            confidence = content.get("confidence")
            signals = content.get("dispute_signals") or []
            cost = outcome.cost
            total_cost += cost

            expected_weight = _expected_weight(case)
            type_total += 1
            if predicted_type == expected_type:
                type_ok += 1
            if expected_weight != "unscored":
                weight_total += 1
                if predicted_weight == expected_weight:
                    weight_ok += 1
            if expected_weight == "potential_dispute":
                dispute_total += 1
                if predicted_weight == "potential_dispute":
                    dispute_ok += 1

            print(
                f"{case_id}: type {expected_type}->{predicted_type} | "
                f"weight {expected_weight}->{predicted_weight} | "
                f"conf {confidence} | signals {signals} | cost {cost} | "
                f"status {outcome.status}"
            )
            time.sleep(0.2)

        if unavailable:
            print()
            continue

        type_acc = (type_ok / type_total) if type_total else 0.0
        weight_acc = (weight_ok / weight_total) if weight_total else 0.0
        dispute_recall = (dispute_ok / dispute_total) if dispute_total else 0.0
        print(
            f"TOTALS {model}: type_accuracy={type_ok}/{type_total} "
            f"({type_acc:.2%}) weight_accuracy={weight_ok}/{weight_total} "
            f"({weight_acc:.2%}) dispute_recall={dispute_ok}/{dispute_total} "
            f"({dispute_recall:.2%}) total_cost={total_cost}"
        )
        print()
        if type_total > 0:
            any_model_ok = True

    return 0 if any_model_ok else exit_code


if __name__ == "__main__":
    raise SystemExit(main())
