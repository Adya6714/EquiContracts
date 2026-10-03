"""Single source of truth for extracted-field verification transitions."""

from decimal import Decimal
from typing import Literal

VerificationState = Literal["ai_extracted", "needs_review", "verified"]

AUTO_VERIFY_THRESHOLD = Decimal("0.900")


def next_state(*, is_financial: bool, confidence: Decimal | None) -> VerificationState:
    """Choose the post-extraction state.

    Financial fields always require human review. Missing confidence is treated
    as uncertain, not as zero-valued source data.
    """

    if is_financial or confidence is None or confidence < AUTO_VERIFY_THRESHOLD:
        return "needs_review"
    return "verified"


def contradiction_state(current_state: VerificationState) -> VerificationState:
    """Pull a contradicted verified field back across the trust boundary."""

    if current_state == "verified":
        return "needs_review"
    return current_state


def can_human_verify(*, is_financial: bool, verified_by: object | None) -> bool:
    return not is_financial or verified_by is not None
