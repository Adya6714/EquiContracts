"""Human-readable project code and inbound-address generation."""

import re
import secrets

from .config import get_settings


def normalize_city_code(value: str) -> str:
    code = re.sub(r"[^A-Za-z]", "", value).upper()
    if len(code) != 3:
        raise ValueError("city_code must contain exactly three letters")
    return code


def generate_project_code(city_code: str) -> str:
    return f"EC-{normalize_city_code(city_code)}-{secrets.randbelow(1000):03d}"


def inbound_alias_for(project_code: str, name: str) -> str:
    """Return the plus-address alias only (no mailbox, no domain)."""
    code = re.sub(r"[^A-Za-z0-9]", "", project_code).lower()
    slug = re.sub(r"[^A-Za-z0-9]", "", name).lower()
    if not code:
        raise ValueError("project_code must contain letters or numbers")
    if not slug:
        raise ValueError("project name must contain letters or numbers")
    return f"{code}{slug[:40]}"


def display_inbound_address(alias: str) -> str:
    """User-facing shared-inbox address: projects+{alias}@domain."""
    settings = get_settings()
    return f"{settings.inbound_mailbox}+{alias}@{settings.inbound_email_domain}"
