import re

import pytest

from apps.api.app.core.config import get_settings
from apps.api.app.core.project_code import (
    display_inbound_address,
    generate_project_code,
    inbound_alias_for,
    normalize_city_code,
)


def test_project_code_format() -> None:
    assert re.fullmatch(r"EC-MUM-\d{3}", generate_project_code("mum"))


def test_city_code_rejects_non_three_letter_value() -> None:
    with pytest.raises(ValueError):
        normalize_city_code("Mumbai")


def test_inbound_alias_is_lowercased_code_plus_slugified_name() -> None:
    alias = inbound_alias_for("EC-MUM-101", "Lodha / Supremus")
    assert alias == "ecmum101lodhasupremus"
    assert "@" not in alias
    assert "+" not in alias


def test_display_inbound_address_uses_shared_mailbox_plus_alias() -> None:
    settings = get_settings()
    assert (
        display_inbound_address("ecmum101")
        == f"{settings.inbound_mailbox}+ecmum101@{settings.inbound_email_domain}"
    )
