"""Cross-source identity for a named civic service's first-month milestone.

Problem: two newsrooms can reuse one video and cover the same monthly result
with very different angles (recipient interview versus aggregate service count).
Neither different text nor media URL is proof of a new event.

The positive match requires independent corroboration: the same named facility,
the same first-month milestone, the same explicit location, separate sources,
and publication within 48 hours. A genuinely new service/location update stays
eligible. No binary/video guesses, and no general same-topic suppression.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any


_FACILITY = re.compile(
    r"(?iu)\b(?:простір|простору|просторі|центр|центру|центрі|хаб|хабу)\s+"
    r"[«“]?[^\n.!?;]{5,100}"
)
_TOKEN = re.compile(r"(?iu)[а-яіїєґ]{4,}")
_STOP = frozenset((
    "для", "про", "вони", "вже", "який", "яка", "яких", "їхні", "свої",
    "громади", "громада", "роботи", "місяць", "місяця", "перший", "першого",
    "відкрили", "відкрито", "завершив", "завершила", "надають", "працює",
    "запоріжжі", "запоріжжя", "новий", "нового", "більше", "понад",
))
_FIRST_MONTH = re.compile(
    r"(?iu)\b(?:перш\w*\s+міся(?:ць|ц\w*)|"
    r"міся(?:ць|ц\w*)\s+тому|"
    r"вже\s+міся(?:ць|ц\w*)|"
    r"за\s+(?:цей|перший)\s+міся(?:ць|ц\w*))"
)
_MULTIPLE_MONTHS = re.compile(r"(?iu)\\b(?:два|двох|дві|три|чотири|кілька|2|3|4)\\s+місяц\\w*\\s+тому")
_LOCATION = re.compile(r"\b(?:[УВув]|місті)\s+([А-ЯІЇЄҐ][а-яіїєґ'’-]{3,})")
_NEW_PHASE = re.compile(
    r"(?iu)\b(?:відкрили\s+(?:нов(?:у|ий)|ще\s+одн(?:у|ин)|друг(?:у|ий))\s+"
    r"(?:філі\w*|локаці\w*|центр\w*|простір)|"
    r"запустили\s+нов\w*\s+послуг\w*|"
    r"відтепер\s+доступн\w*\s+нов\w*\s+послуг\w*|"
    r"переїхав\w*\s+за\s+нов\w*\s+адрес\w*)"
)


def _get(row: Any, field: str) -> str:
    try:
        value = row[field]
    except (KeyError, IndexError, TypeError):
        value = getattr(row, field, "")
    return str(value or "")


def _source_story(row: Any) -> str:
    # Source-owned text, not an AI rewrite that can invent a shared theme.
    return "\n".join((_get(row, "title"), _get(row, "raw_text")))[:8000]


def _stem(token: str) -> str:
    value = token.casefold()
    for start, norm in (
        ("ветеран", "ветеран"), ("турбот", "турбот"), ("простор", "простір"),
        ("простір", "простір"), ("центр", "центр"), ("підтрим", "підтрим"),
    ):
        if value.startswith(start):
            return norm
    return value[:6]


def _facility_key(story: str) -> tuple[str, ...]:
    # The first three content terms of the named venue, *not* the trailing
    # journalist's sentence. Gender/number inflection is normalized by stems.
    for match in _FACILITY.finditer(story):
        terms = [
            _stem(token) for token in _TOKEN.findall(match.group(0))
            if token.casefold() not in _STOP
        ]
        if len(terms) >= 3:
            return tuple(terms[:3])
    return ()


def _location_key(story: str) -> str:
    # Named and capitalized locality after a preposition, in the story lead.
    # No match is intentionally insufficient to assert duplicate identity.
    match = _LOCATION.search(story[:240])
    return _stem(match.group(1)) if match else ""


def _time(row: Any) -> datetime | None:
    # On published-ledger rows there is no source_published_at: the
    # COMMITTED timestamp is the authoritative comparison clock.
    for key in ("source_published_at", "published_at"):
        raw = _get(row, key).strip()
        if not raw:
            continue
        try:
            value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc)
    return None


def civic_milestone_same_event(current: Any, candidate: Any) -> tuple[bool, str]:
    """Same facility + same first-month milestone, or an independent update."""
    left_source = _get(current, "source_id")
    right_source = _get(candidate, "source_id")
    if not left_source or not right_source or left_source == right_source:
        return False, ""
    left, right = _source_story(current), _source_story(candidate)
    if not (_FIRST_MONTH.search(left) and _FIRST_MONTH.search(right)):
        return False, ""
    if _MULTIPLE_MONTHS.search(left) or _MULTIPLE_MONTHS.search(right):
        return False, ""
    facility_left, facility_right = _facility_key(left), _facility_key(right)
    if not facility_left or facility_left != facility_right:
        return False, ""
    locality_left, locality_right = _location_key(left), _location_key(right)
    if not locality_left or locality_left != locality_right:
        return False, ""
    time_left, time_right = _time(current), _time(candidate)
    if not time_left or not time_right:
        return False, ""
    if abs((time_left - time_right).total_seconds()) > 48 * 3600:
        return False, ""
    if _NEW_PHASE.search(left) or _NEW_PHASE.search(right):
        return False, "materially distinct civic service/location update"
    return True, (
        "CIVIC_FIRST_MONTH_DUPLICATE same facility/milestone/locality "
        f"facility={','.join(facility_left)} locality={locality_left}"
    )
