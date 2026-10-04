"""Run one agent with step/retry/cost limits. No LLM. No LangGraph."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID

from packages.agents.context import RunContext
from packages.agents.guardrails import allowlist, autonomy
from packages.agents.guardrails.log_allowlist import LOG_KEY_ALLOWLIST
from packages.agents.tools import get_tool
from packages.agents.tools._base import ToolRefusal

MAX_STEPS_DEFAULT = 10
MAX_RETRIES_DEFAULT = 2
COST_CAP_DEFAULT = Decimal("1.00")

_LOG_KEY_ALLOWLIST = LOG_KEY_ALLOWLIST
_ENUM_VALUE = re.compile(r"^[A-Za-z0-9_./-]{1,64}$")
_UUID_VALUE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


class SelfCheckError(Exception):
    """Agent self-check failed; runtime may retry up to the limit."""

    def __init__(self, code: str = "self_check_failed") -> None:
        self.code = code
        super().__init__(code)


class RunLimitError(Exception):
    """Steps, retries, or cost cap reached."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class ServicesHandleError(Exception):
    """Services handle is missing a required method."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass
class ProposalEmission:
    proposal_type: str
    autonomy_level: int
    proposal_id: UUID | None = None


@dataclass
class _BufferedProposal:
    proposal_type: str
    content: dict[str, Any]
    confidence: Decimal | None
    autonomy_level: int
    emission: ProposalEmission


@dataclass
class RunOutcome:
    status: str  # succeeded | failed | needs_human
    steps_used: int
    retries_used: int
    cost: Decimal
    error: str | None = None
    proposals: list[ProposalEmission] = field(default_factory=list)


@dataclass
class AgentRuntime:
    context: RunContext
    agent_name: str
    max_steps: int = MAX_STEPS_DEFAULT
    max_retries: int = MAX_RETRIES_DEFAULT
    cost_cap: Decimal = COST_CAP_DEFAULT
    cost_per_step: Decimal = Decimal("0")
    _steps: int = 0
    _retries: int = 0
    _cost: Decimal = Decimal("0")
    _buffer: list[_BufferedProposal] = field(default_factory=list)
    _failed: str | None = None

    def call_tool(self, tool_name: str, **kwargs: Any) -> Any:
        self._begin_step()
        safe_in = sanitize_for_log({"tool": tool_name, **kwargs})
        if not allowlist.is_tool_allowed(self.agent_name, tool_name):
            self._log_step(
                tool_called=tool_name,
                outcome="blocked",
                input_payload=safe_in,
                output_payload={"reason": "not_on_allowlist"},
            )
            raise ToolRefusal("not_on_allowlist")

        tool = get_tool(tool_name)
        if tool is None:
            self._log_step(
                tool_called=tool_name,
                outcome="error",
                input_payload=safe_in,
                output_payload={"reason": "unknown_tool"},
            )
            raise ToolRefusal("unknown_tool")

        try:
            result = tool(self.context, **kwargs)
        except ToolRefusal as exc:
            self._log_step(
                tool_called=tool_name,
                outcome="blocked",
                input_payload=safe_in,
                output_payload={"reason": getattr(exc, "code", "refused")},
            )
            raise
        except Exception:
            self._log_step(
                tool_called=tool_name,
                outcome="error",
                input_payload=safe_in,
                output_payload={"reason": "tool_error"},
            )
            raise

        self._log_step(
            tool_called=tool_name,
            outcome="ok",
            input_payload=safe_in,
            output_payload=sanitize_for_log(result if isinstance(result, dict) else {}),
        )
        return result

    def emit_proposal(
        self,
        proposal_type: str,
        content: dict[str, Any],
        confidence: Decimal | None = None,
    ) -> ProposalEmission:
        """Buffer a proposal. Autonomy looked up; not applied or written yet."""

        self._begin_step()
        level = autonomy.autonomy_level_for(proposal_type)
        emission = ProposalEmission(
            proposal_type=proposal_type,
            autonomy_level=level,
        )
        self._buffer.append(
            _BufferedProposal(
                proposal_type=proposal_type,
                content=content,
                confidence=confidence,
                autonomy_level=level,
                emission=emission,
            )
        )
        self._log_step(
            tool_called="emit_proposal",
            outcome="ok",
            input_payload=sanitize_for_log(
                {
                    "proposal_type": proposal_type,
                    "autonomy_level": level,
                }
            ),
            output_payload=sanitize_for_log({"outcome": "buffered"}),
        )
        return emission

    def discard_proposals(self) -> None:
        self._buffer.clear()

    def flush_proposals(self) -> list[ProposalEmission]:
        """Write buffered proposals to the database. Call only on success."""

        create = getattr(self.context.services, "create_proposal", None)
        if create is None:
            raise ServicesHandleError("missing_create_proposal")
        written: list[ProposalEmission] = []
        for item in self._buffer:
            proposal_id = create(
                run_id=self.context.run_id,
                org_id=self.context.org_id,
                engagement_id=self.context.engagement_id,
                proposal_type=item.proposal_type,
                content=item.content,
                autonomy_level=item.autonomy_level,
                confidence=item.confidence,
            )
            item.emission.proposal_id = UUID(str(proposal_id))
            written.append(item.emission)
        self._buffer.clear()
        return written

    def _begin_step(self) -> None:
        if self._steps >= self.max_steps:
            self._failed = "max_steps"
            raise RunLimitError("max_steps")
        self._steps += 1
        self._cost += self.cost_per_step
        if self._cost > self.cost_cap:
            self._failed = "cost_cap"
            self._log_step(
                tool_called=None,
                outcome="error",
                input_payload={},
                output_payload={"reason": "cost_cap"},
            )
            raise RunLimitError("cost_cap")

    def _log_step(
        self,
        *,
        tool_called: str | None,
        outcome: str,
        input_payload: dict[str, Any],
        output_payload: dict[str, Any],
    ) -> None:
        log = getattr(self.context.services, "record_step", None)
        if log is None:
            raise ServicesHandleError("missing_record_step")
        log(
            run_id=self.context.run_id,
            org_id=self.context.org_id,
            step_no=self._steps,
            outcome=outcome,
            tool_called=tool_called,
            input_payload=input_payload,
            output_payload=output_payload,
        )


def sanitize_for_log(payload: dict[str, Any]) -> dict[str, Any]:
    """Allowlist keys and safe scalar values only."""

    safe: dict[str, Any] = {}
    for key, value in payload.items():
        key_s = str(key)
        key_l = key_s.lower()
        if not (key_l.endswith("_id") or key_l in _LOG_KEY_ALLOWLIST):
            continue
        if isinstance(value, bool) or (
            isinstance(value, int) and not isinstance(value, bool)
        ):
            safe[key_s] = value
        elif isinstance(value, UUID):
            safe[key_s] = str(value)
        elif isinstance(value, str):
            if _UUID_VALUE.fullmatch(value) or _ENUM_VALUE.fullmatch(value):
                safe[key_s] = value
        elif value is None and key_l.endswith("_id"):
            safe[key_s] = None
    return safe


def _safe_error(exc: BaseException) -> str:
    """Exception class name plus a short safe code. Never include str(exc)."""

    name = type(exc).__name__
    code = getattr(exc, "code", None)
    if isinstance(code, str) and _ENUM_VALUE.fullmatch(code):
        return f"{name}:{code}"
    return f"{name}:error"


def _require_services(context: RunContext) -> None:
    services = context.services
    if getattr(services, "record_step", None) is None:
        raise ServicesHandleError("missing_record_step")
    if getattr(services, "create_proposal", None) is None:
        raise ServicesHandleError("missing_create_proposal")


def run_agent(
    context: RunContext,
    *,
    agent_name: str,
    agent_fn: Callable[[AgentRuntime], None],
    max_steps: int = MAX_STEPS_DEFAULT,
    max_retries: int = MAX_RETRIES_DEFAULT,
    cost_cap: Decimal = COST_CAP_DEFAULT,
    cost_per_step: Decimal = Decimal("0"),
) -> RunOutcome:
    """Execute one agent with self-check retries and hard limits."""

    _require_services(context)

    runtime = AgentRuntime(
        context=context,
        agent_name=agent_name,
        max_steps=max_steps,
        max_retries=max_retries,
        cost_cap=cost_cap,
        cost_per_step=cost_per_step,
    )

    while True:
        try:
            agent_fn(runtime)
            if runtime._failed:
                raise RunLimitError(runtime._failed)
            proposals = runtime.flush_proposals()
            return RunOutcome(
                status="succeeded",
                steps_used=runtime._steps,
                retries_used=runtime._retries,
                cost=runtime._cost,
                proposals=proposals,
            )
        except SelfCheckError as exc:
            runtime.discard_proposals()
            if runtime._retries >= max_retries:
                return RunOutcome(
                    status="failed",
                    steps_used=runtime._steps,
                    retries_used=runtime._retries,
                    cost=runtime._cost,
                    error=_safe_error(RunLimitError("max_retries")),
                    proposals=[],
                )
            _ = exc
            runtime._retries += 1
            continue
        except ServicesHandleError:
            raise
        except (RunLimitError, ToolRefusal) as exc:
            runtime.discard_proposals()
            return RunOutcome(
                status="failed",
                steps_used=runtime._steps,
                retries_used=runtime._retries,
                cost=runtime._cost,
                error=_safe_error(exc),
                proposals=[],
            )
        except Exception as exc:  # noqa: BLE001 — surface as failed run
            runtime.discard_proposals()
            return RunOutcome(
                status="failed",
                steps_used=runtime._steps,
                retries_used=runtime._retries,
                cost=runtime._cost,
                error=_safe_error(exc),
                proposals=[],
            )
