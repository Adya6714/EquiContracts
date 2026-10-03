"""Conservative registry for fields that always require human review."""

FINANCIAL_FIELDS = frozenset(
    {
        "value",
        "bg_value",
        "expiry_date",
        "claim_expiry_date",
        "gross_amount",
        "certified_amount",
        "net_payable",
        "amount_received",
        "tds",
        "wct",
        "retention",
        "cgst",
        "sgst",
        "igst",
        "total_value",
        "rupees_at_risk",
    }
)

FINANCIAL_HINTS = (
    "amount",
    "value",
    "price",
    "rate",
    "tax",
    "gst",
    "tds",
    "wct",
    "retention",
    "deduction",
    "outstanding",
    "interest",
)


def is_financial_field(field_name: str) -> bool:
    normalized = field_name.strip().lower()
    return normalized in FINANCIAL_FIELDS or any(
        hint in normalized for hint in FINANCIAL_HINTS
    )
