"""2.3.7: prevent unrelated template similarity and material civic updates from vanishing.

Narrow source-owned facts only. This module never creates a publication or
mutates historical decisions. No AI guesswork, geography keyword bans, or
cross-channel policy overrides.
"""
from __future__ import annotations

import html
import re
from typing import Any

_MONTHS = (
    "січня", "лютого", "березня", "квітня", "травня", "червня",
    "липня", "серпня", "вересня", "жовтня", "листопада", "грудня",
)
_DATE = re.compile(
    r"(?iu)(?<!\d)(?P<days>\d{1,2}(?:\s*,\s*\d{1,2})*"
    r"(?:\s*(?:та|і|й|–|-)\s*\d{1,2})?)\s+"
    r"(?P<month>" + "|".join(_MONTHS) + r")\b"
)
_PROMO_TAIL = re.compile(
    r"(?iu)(?:ми\s+в|підписуйтесь\s+на\s+нас|стежте\s+за\s+нами)\s*"
    r"(?:[📲👇:\-–]|https?://|whatsapp|instagram|tiktok|threads)"
)
_LINK = re.compile(r"https?://[^\s<>()]+", re.I)
_SOCIAL_TERMS = re.compile(r"(?iu)\b(?:whatsapp|instagram|tiktok|tik-tok|threads|facebook)\b")
_CASUALTY = {
    "killed": re.compile(r"(?iu)(?<!\d)(\d{1,4})\s+(?:люд(?:ей|ини)?\s+)?загибл\w*|(?:загибл\w*|загинул\w*)\s+(\d{1,4})"),
    "wounded": re.compile(r"(?iu)(?<!\d)(\d{1,4})\s+(?:люд(?:ей|ини)?\s+)?(?:поранен|постраждал)\w*|(?:поранен|постраждал)\w*\s+(\d{1,4})"),
    "missing": re.compile(r"(?iu)(?<!\d)(\d{1,4})\s+(?:люд(?:ей|ини)?\s+)?(?:зникл|безвіст)\w*|(?:зникл|безвіст)\w*\s+(\d{1,4})"),
}
_TRANSPORT = re.compile(r"(?iu)\b(?:автобус\w*|тролейбус\w*|трамва\w*|громадськ\w*\s+транспорт\w*)\b")
_ROUTE = re.compile(r"(?iu)\b(?:автобус\w*|тролейбус\w*|трамва\w*)\s*№\s*(\d{1,3})")
_MOURNING = re.compile(r"(?iu)\b(?:жалоб\w*|загибл\w*|загинул\w*|жертв\w*)\b")


def _get(row: Any, field: str) -> str:
    try:
        value = row[field]
    except (KeyError, TypeError, IndexError):
        value = getattr(row, field, "")
    return str(value or "")


def source_event_text(row: Any) -> str:
    """Use only source headline and source body, never model-generated final copy."""
    title = html.unescape(_get(row, "title")).strip()
    raw = html.unescape(_get(row, "raw_text")).strip()
    if raw.startswith(title):
        return raw
    return "\n".join(item for item in (title, raw) if item)


def clean_event_boilerplate_237(value: str) -> str:
    """Drop recurring social-channel advertising, NOT the event details."""
    source = html.unescape(str(value or ""))
    tail = _PROMO_TAIL.search(source)
    if tail:
        source = source[:tail.start()]
    source = _LINK.sub(" ", source)
    source = _SOCIAL_TERMS.sub(" ", source)
    return re.sub(r"\s+", " ", source).strip()


def _days(text: str) -> frozenset[tuple[int, int]]:
    found: set[tuple[int, int]] = set()
    for m in _DATE.finditer(text):
        month = _MONTHS.index(m.group("month").casefold()) + 1
        for token in re.findall(r"\d{1,2}", m.group("days")):
            day = int(token)
            if 1 <= day <= 31:
                found.add((month, day))
    return frozenset(found)


def _counts(text: str, kind: str) -> frozenset[int]:
    return frozenset(int(m.group(1) or m.group(2)) for m in _CASUALTY[kind].finditer(text))


def material_monitoring_update_237(current: Any, candidate: Any) -> str:
    """Reasons why a monitoring item must NOT be suppressed as a duplicate.

    Strictly require two source texts and recognizable event categories; a
    headline by itself is not proof of a material update. Matching source URLs
    are intentionally not exempt (official sources can edit developing facts).
    """
    left = clean_event_boilerplate_237(source_event_text(current)).casefold()
    right = clean_event_boilerplate_237(source_event_text(candidate)).casefold()
    if len(left) < 35 or len(right) < 35:
        return ""
    left_transit = bool(_TRANSPORT.search(left))
    right_transit = bool(_TRANSPORT.search(right))
    if left_transit and right_transit:
        days_left = _days(left)
        days_right = _days(right)
        if days_left and days_right and days_left.isdisjoint(days_right):
            return "MONITORING_NEW_TRANSPORT_SERVICE_DATE_237"
        routes_a = set(_ROUTE.findall(left))
        routes_b = set(_ROUTE.findall(right))
        if routes_a and routes_b and routes_a.isdisjoint(routes_b):
            return "MONITORING_DISTINCT_TRANSPORT_ROUTES_237"
    if _MOURNING.search(left) and _MOURNING.search(right):
        for kind in ("killed", "wounded", "missing"):
            a = _counts(left, kind)
            b = _counts(right, kind)
            if a and b and max(a) != max(b):
                return "MONITORING_MATERIAL_CASUALTY_UPDATE_237"
        if (re.search(r"жалоб", left) and re.search(r"жалоб", right)):
            days_left = _days(left)
            days_right = _days(right)
            if days_left and days_right and days_left != days_right:
                return "MONITORING_MOURNING_DATES_UPDATED_237"
    return ""


__all__ = ["source_event_text", "clean_event_boilerplate_237", "material_monitoring_update_237"]
