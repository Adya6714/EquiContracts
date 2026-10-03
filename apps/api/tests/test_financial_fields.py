from apps.api.app.core.financial_fields import is_financial_field


def test_registered_money_field_is_financial() -> None:
    assert is_financial_field("certified_amount")


def test_unknown_money_shaped_field_is_conservative() -> None:
    assert is_financial_field("future_interest_exposure")


def test_consequential_bg_date_is_treated_as_financial() -> None:
    assert is_financial_field("claim_expiry_date")


def test_routine_date_field_is_not_financial() -> None:
    assert not is_financial_field("received_at")
