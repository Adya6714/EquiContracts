"""Every number/date in text must appear in the allowed sourced set.

Understands Indian money formats and whole dates (day/month order, month names).
Every digit in the text must be consumed by an allowed amount, date, plain
number, or percentage.
"""

from __future__ import annotations

import re
from contextlib import suppress
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

_MONTH_MAP = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}
_MONTH_ALT = "|".join(sorted(_MONTH_MAP, key=len, reverse=True))

# Whole-date patterns. Numeric dates are day/month/year only (never month/day).
_DATE_REGEXES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(\d{4}-\d{2}-\d{2})\b"), "iso"),
    (re.compile(r"\b(\d{1,2}/\d{1,2}/\d{4})\b"), "dmy_slash"),
    (re.compile(r"\b(\d{1,2}-\d{1,2}-\d{4})\b"), "dmy_dash"),
    (
        re.compile(
            rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH_ALT})\s+(\d{{4}})\b",
            re.IGNORECASE,
        ),
        "d_month_y",
    ),
    (
        re.compile(
            rf"\b({_MONTH_ALT})\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b",
            re.IGNORECASE,
        ),
        "month_d_y",
    ),
    (
        re.compile(
            rf"\b(\d{{1,2}})-({_MONTH_ALT})-(\d{{4}})\b",
            re.IGNORECASE,
        ),
        "d_mon_y_dash",
    ),
)

# Indian grouping: last group of 3, then groups of 2 (e.g. 1,70,80,000).
_INDIAN_NUM = r"\d{1,3}(?:,\d{2})*,\d{3}(?:\.\d+)?"
_WESTERN_NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?"
_PLAIN_DEC = r"\d+(?:\.\d+)?"

_MONEY_PATTERNS = (
    re.compile(
        rf"(?i)(?:₹|rs\.?\s*)?\s*"
        rf"({_INDIAN_NUM}|{_WESTERN_NUM}|{_PLAIN_DEC})"
        rf"\s*(crores?|cr|lakhs?|lacs?|l)\b"
    ),
    re.compile(
        rf"(?i)(?:₹|rs\.?\s*)\s*"
        rf"({_INDIAN_NUM}|{_WESTERN_NUM}|{_PLAIN_DEC})\b"
    ),
    re.compile(rf"\b({_INDIAN_NUM})\b"),
    re.compile(rf"\b({_WESTERN_NUM})\b"),
    re.compile(r"\b(\d+\.\d{2})\b"),
)

_PERCENT_PATTERN = re.compile(r"\b(\d+(?:\.\d+)?)\s*%")
_PLAIN_NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?")


def _parse_dmy(day: int, month: int, year: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _parse_date_token(token: str) -> date | None:
    token = token.strip()
    try:
        return datetime.strptime(token, "%Y-%m-%d").date()
    except ValueError:
        pass
    for fmt in ("%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(token, fmt).date()
        except ValueError:
            continue
    # Month-name forms
    for pattern, kind in _DATE_REGEXES:
        if kind in {"iso", "dmy_slash", "dmy_dash"}:
            continue
        match = pattern.fullmatch(token)
        if match is None:
            # Also try searching as full string via parse helpers below
            continue
    m = re.fullmatch(
        rf"(?i)(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH_ALT})\s+(\d{{4}})",
        token,
    )
    if m:
        return _parse_dmy(
            int(m.group(1)), _MONTH_MAP[m.group(2).lower()], int(m.group(3))
        )
    m = re.fullmatch(
        rf"(?i)({_MONTH_ALT})\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})",
        token,
    )
    if m:
        return _parse_dmy(
            int(m.group(2)), _MONTH_MAP[m.group(1).lower()], int(m.group(3))
        )
    m = re.fullmatch(
        rf"(?i)(\d{{1,2}})-({_MONTH_ALT})-(\d{{4}})",
        token,
    )
    if m:
        return _parse_dmy(
            int(m.group(1)), _MONTH_MAP[m.group(2).lower()], int(m.group(3))
        )
    return None


def _strip_grouping(raw: str) -> str:
    return raw.replace(",", "")


def _unit_multiplier(unit: str) -> Decimal:
    u = unit.lower()
    if u in {"l", "lac", "lacs", "lakh", "lakhs"}:
        return Decimal("100000")
    if u in {"cr", "crore", "crores"}:
        return Decimal("10000000")
    return Decimal("1")


def normalize_amount(value: Any) -> Decimal | None:
    """Parse one allowed or text amount into Decimal rupees."""

    if isinstance(value, Decimal):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return Decimal(value)
    if isinstance(value, float):
        return None
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or text.endswith("%"):
        return None
    m = re.fullmatch(
        rf"(?i)(?:₹|rs\.?\s*)?\s*"
        rf"({_INDIAN_NUM}|{_WESTERN_NUM}|{_PLAIN_DEC})"
        rf"\s*(crores?|cr|lakhs?|lacs?|l)?",
        text,
    )
    if m:
        number = Decimal(_strip_grouping(m.group(1)))
        unit = m.group(2) or ""
        return number * _unit_multiplier(unit) if unit else number
    try:
        return Decimal(_strip_grouping(text))
    except InvalidOperation:
        return None


def _normalize_allowed(
    allowed: set[Any],
) -> tuple[set[Decimal], set[date], set[Decimal], set[Decimal]]:
    """Return (money_amounts, dates, plain_numbers, percents)."""

    amounts: set[Decimal] = set()
    dates: set[date] = set()
    plains: set[Decimal] = set()
    percents: set[Decimal] = set()
    for item in allowed:
        if isinstance(item, date) and not isinstance(item, datetime):
            dates.add(item)
            continue
        if isinstance(item, datetime):
            dates.add(item.date())
            continue
        if isinstance(item, str):
            stripped = item.strip()
            if stripped.endswith("%"):
                with suppress(InvalidOperation):
                    percents.add(Decimal(stripped[:-1].strip()))
                continue
            parsed_date = _parse_date_token(stripped)
            if parsed_date is not None:
                dates.add(parsed_date)
                continue
            # Indian/Western money with grouping or units → amount
            if re.search(r"(?i)₹|rs\.?|\d,\d|lakh|lac|\bl\b|crore|\bcr\b", stripped):
                amount = normalize_amount(stripped)
                if amount is not None:
                    amounts.add(amount)
                    continue
            amount = normalize_amount(stripped)
            if amount is not None:
                # Bare numbers in the allowed set count as plain (and money if large).
                plains.add(amount)
                amounts.add(amount)
            continue
        if isinstance(item, (int, Decimal)) and not isinstance(item, bool):
            value = Decimal(item) if not isinstance(item, Decimal) else item
            plains.add(value)
            amounts.add(value)
    return amounts, dates, plains, percents


def _mark_span(occupied: list[bool], start: int, end: int) -> None:
    for i in range(start, end):
        occupied[i] = True


def _span_free(occupied: list[bool], start: int, end: int) -> bool:
    return not any(occupied[i] for i in range(start, end))


def _extract_date_at(match: re.Match[str], kind: str) -> date | None:
    if kind == "iso":
        return _parse_date_token(match.group(1))
    if kind == "dmy_slash":
        day_s, month_s, year_s = match.group(1).split("/")
        try:
            return _parse_dmy(int(day_s), int(month_s), int(year_s))
        except ValueError:
            return None
    if kind == "dmy_dash":
        day_s, month_s, year_s = match.group(1).split("-")
        try:
            return _parse_dmy(int(day_s), int(month_s), int(year_s))
        except ValueError:
            return None
    if kind == "d_month_y":
        return _parse_dmy(
            int(match.group(1)),
            _MONTH_MAP[match.group(2).lower()],
            int(match.group(3)),
        )
    if kind == "month_d_y":
        return _parse_dmy(
            int(match.group(2)),
            _MONTH_MAP[match.group(1).lower()],
            int(match.group(3)),
        )
    if kind == "d_mon_y_dash":
        return _parse_dmy(
            int(match.group(1)),
            _MONTH_MAP[match.group(2).lower()],
            int(match.group(3)),
        )
    return None


def numbers_and_dates_ok(text: str, allowed: set[Any]) -> bool:
    """True iff every digit is part of an allowed date/amount/number/percent."""

    amounts, dates, plains, percents = _normalize_allowed(allowed)
    occupied = [False] * len(text)

    # 1. Dates (whole spans).
    for pattern, kind in _DATE_REGEXES:
        for match in pattern.finditer(text):
            if not _span_free(occupied, match.start(), match.end()):
                continue
            parsed = _extract_date_at(match, kind)
            if parsed is None:
                continue
            if parsed not in dates:
                return False
            _mark_span(occupied, match.start(), match.end())

    # 2. Money amounts (with units / grouping / currency).
    for pattern in _MONEY_PATTERNS:
        for match in pattern.finditer(text):
            if not _span_free(occupied, match.start(), match.end()):
                continue
            groups = match.groups()
            raw = groups[0]
            unit = groups[1] if len(groups) > 1 and groups[1] else ""
            try:
                number = Decimal(_strip_grouping(raw))
            except InvalidOperation:
                continue
            amount = number * _unit_multiplier(unit) if unit else number
            if amount not in amounts:
                return False
            _mark_span(occupied, match.start(), match.end())

    # 3. Percentages.
    for match in _PERCENT_PATTERN.finditer(text):
        if not _span_free(occupied, match.start(), match.end()):
            continue
        try:
            value = Decimal(match.group(1))
        except InvalidOperation:
            return False
        if value not in percents:
            return False
        _mark_span(occupied, match.start(), match.end())

    # 4. Remaining plain numbers (any length: days, counts, years).
    for match in _PLAIN_NUMBER_PATTERN.finditer(text):
        if not _span_free(occupied, match.start(), match.end()):
            continue
        try:
            value = Decimal(match.group(0))
        except InvalidOperation:
            return False
        if value not in plains and value not in amounts:
            return False
        _mark_span(occupied, match.start(), match.end())

    # 5. Any leftover digit fails.
    for index, char in enumerate(text):
        if char.isdigit() and not occupied[index]:
            return False
    return True
