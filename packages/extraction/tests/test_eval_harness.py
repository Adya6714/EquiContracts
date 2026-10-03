from packages.extraction.eval_harness import score_fields, validate_fixtures


def test_financial_and_non_financial_scored_separately() -> None:
    expected = {
        "fields": {
            "bg_number": {"value": "BG-1", "financial": False},
            "value": {"value": "100.00", "financial": True},
        }
    }
    actual = {
        "fields": {
            "bg_number": {"value": "BG-1"},
            "value": {"value": "99.00"},
        }
    }

    assert score_fields(expected, actual, financial=False).ratio == 1
    assert score_fields(expected, actual, financial=True).ratio == 0


def test_frozen_fixture_manifest_is_valid() -> None:
    assert validate_fixtures() == 0
