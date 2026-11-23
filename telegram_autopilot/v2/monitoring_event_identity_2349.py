"""2.3.49: evidence-based incident identity across independent monitoring sources.

Only source title/body, never generated captions or source identity, establish facts.
This is a narrow rescue-incident lane in the channel-configured global deduper,
not a blacklist for any particular city, source or rescuer.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from typing import Any


def _get(row: Any, key: str) -> str:
    try:
        value = row[key]
    except (KeyError, IndexError, TypeError):
        value = getattr(row, key, "")
    return str(value or "")


def _source(row: Any) -> str:
    return " ".join((_get(row, "title"), _get(row, "raw_text")[:6000]))


def _timestamp(row: Any) -> datetime | None:
    for field in ("source_published_at", "published_at"):
        value = _get(row, field).strip()
        if not value:
            continue
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is not None:
            return parsed.astimezone(timezone.utc)
    return None


# Distinctive incident attributes must agree; a shared topic or city is not enough.
_RESCUE = re.compile(r"(?iu)\b(?:рятув\w*|врятув\w*|порятун\w*|евакуювал\w*|евакуац\w*|витягл\w*|дістал\w*|rescu\w*|evacuat\w*)")
_BOAT = re.compile(r"(?iu)\b(?:човн\w*|човен|човна|катер\w*|плавзасоб\w*|boat\w*|vessel\w*)")
_INJURY = re.compile(r"(?iu)\b(?:травм\w*|перелом\w*|зламал\w*|ушкоджен\w*|поранен\w*|injur\w*|fractur\w*)")
_ROCK = re.compile(r"(?iu)\b(?:скел\w*|скеля\w*|скеляст\w*|кам'янист\w*|rock\w*|cliff\w*)")
_SHORE = re.compile(r"(?iu)\b(?:берег\w*|узбереж\w*|прибереж\w*|остров\w*|shore\w*|riverbank\w*)")
_WOMAN = re.compile(r"(?iu)\b(?:жін\w*|дівчин\w*|woman|female)\b")
_MAN = re.compile(r"(?iu)\b(?:чолов\w*|хлопц\w*|man|male)\b")
_CHILD = re.compile(r"(?iu)\b(?:дитин\w*|дітей|підлітк\w*|child\w*|teen\w*)")
_OUTCOME = re.compile(r"(?iu)\b(?:померл\w*|загинул\w*|загибл\w*|death|died|fatalit\w*)")
_DISTRICT = re.compile(r"\b([А-ЯІЇЄҐ][А-Яа-яІЇЄҐіїєґ'’\-]{4,})\s+(?:район\w*|громад\w*)\b")
_WATER = re.compile(r"\b(?:берег\w*|узбереж\w*|річк\w*)\s+(?:(?:річк\w*|водосховищ\w*)\s+)?([А-ЯІЇЄҐ][А-Яа-яІЇЄҐіїєґ'’\-]{3,})\b")


def _stem(value: str) -> str:
    # A stable local-name root without hardcoding a district or river name.
    name = value.casefold().replace("’", "'")
    return name[:7] if len(name) >= 8 else name


def _places(source: str) -> tuple[set[str], set[str]]:
    return ({_stem(x) for x in _DISTRICT.findall(source)},
            {_stem(x) for x in _WATER.findall(source)})


def _victim(source: str) -> str:
    kinds = [name for name, regex in (("woman", _WOMAN), ("man", _MAN), ("child", _CHILD))
             if regex.search(source)]
    return kinds[0] if len(kinds) == 1 else ""


def rescue_same_event_2349(current: Any, previous: Any) -> tuple[bool, str]:
    """Confirm a distinctive rescue event, preserving distinct incidents and updates.

    Requires a dated, source-backed rescue with matching method, injury, terrain,
    place and victim where explicit. Missing/contradictory place is not proof.
    """
    a, b = _source(current), _source(previous)
    if not a.strip() or not b.strip():
        return False, ""
    when_a, when_b = _timestamp(current), _timestamp(previous)
    if when_a is None or when_b is None or abs(when_a - when_b) > timedelta(hours=48):
        return False, ""
    if not all(regex.search(a) and regex.search(b)
               for regex in (_RESCUE, _BOAT, _INJURY, _ROCK, _SHORE)):
        return False, ""
    actor_a, actor_b = _victim(a), _victim(b)
    if actor_a and actor_b and actor_a != actor_b:
        return False, ""
    # A confirmed newly fatal outcome is an update, not a republication.
    if _OUTCOME.search(a) and not _OUTCOME.search(b):
        return False, "new confirmed fatal outcome"
    districts_a, waters_a = _places(a)
    districts_b, waters_b = _places(b)
    if districts_a and districts_b and districts_a.isdisjoint(districts_b):
        return False, ""
    if waters_a and waters_b and waters_a.isdisjoint(waters_b):
        return False, ""
    common_districts = districts_a & districts_b
    common_waters = waters_a & waters_b
    if not common_districts and not common_waters:
        return False, ""
    return True, "2.3.49 source-owned rescue+injury+boat+terrain+geography within 48h"


__all__ = ["rescue_same_event_2349"]
