"""Cross-source identity for verified military-remains repatriation announcements.

Use facts from source text, not rewritten captions or publisher branding.
A distinctive returned-remains count plus subject/action and a tight time
window identifies one announcement even if its two headlines share few words.
Later identification, family handovers and new repatriation rounds are updates.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import re
from typing import Any

_RETURN = re.compile(r"(?iu)\b(?:повернул\w*|повернен\w*|репатріаці\w*|репатрійован\w*|передал\w*|repatriat\w*|returned|returning)\b")
_REMAINS = re.compile(r"(?iu)\b(?:тіл\w*|остан\w*|рештк\w*|bodies|remains)\b")
_SERVICE = re.compile(r"(?iu)\b(?:військов\w*|військовослужбовц\w*|загибл\w*|полегл\w*|soldiers?|servicemen|servicewomen|fallen)\b")
_COUNT = re.compile(
    r"(?iu)\b(?:тіл\w*|остан\w*|рештк\w*|bodies|remains)\W+(?:ще\W+)?(?P<after>\d{2,4})\b"
    r"|\b(?P<before>\d{2,4})\W+(?:(?:люд\w*|військов\w*|українц\w*)\W+)?"
    r"(?:тіл\w*|остан\w*|рештк\w*|bodies|remains)\b"
)
_PHASE_UPDATE = re.compile(
    r"(?iu)\b(?:ідентифікувал\w*|ідентифікован\w*|встановил\w*\s+імен\w*|"
    r"передал\w*\s+родин\w*|похован\w*|прощан\w*|"
    r"нов\w*\s+(?:етап\w*|обмін\w*|парті\w*)|наступн\w*\s+(?:етап\w*|обмін\w*|парті\w*))\b"
)


def _get(row: Any, key: str) -> str:
    try:
        value = row[key]
    except (KeyError, IndexError, TypeError):
        value = getattr(row, key, "")
    return str(value or "")


def _original(row: Any) -> str:
    return (_get(row, "title") + "\n" + _get(row, "raw_text"))[:4200].casefold()


def remains_return_count(text: str) -> int | None:
    if not (_RETURN.search(text) and _REMAINS.search(text) and _SERVICE.search(text)):
        return None
    match = _COUNT.search(text)
    if match is None:
        return None
    count = int(match.group("after") or match.group("before"))
    return count if count >= 10 else None


def _event_time(row: Any) -> datetime | None:
    for key in ("source_published_at", "published_at", "discovered_at"):
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


def repatriation_same_event(current: Any, candidate: Any) -> tuple[bool, str]:
    """Same repatriation round, independently confirmed across two publishers."""
    source_a = _get(current, "source_id")
    source_b = _get(candidate, "source_id")
    if source_a and source_b and source_a == source_b:
        return False, "same publisher: use ordinary duplicate matching"
    a, b = _original(current), _original(candidate)
    count_a, count_b = remains_return_count(a), remains_return_count(b)
    if count_a is None or count_b is None or count_a != count_b:
        return False, "distinct or unverified repatriation count"
    if _PHASE_UPDATE.search(a) or _PHASE_UPDATE.search(b):
        return False, "material follow-up or new repatriation round"
    ta, tb = _event_time(current), _event_time(candidate)
    if ta is None or tb is None:
        return False, "repatriation event times unavailable"
    if abs(ta - tb) > timedelta(hours=6):
        return False, "outside six-hour repatriation announcement window"
    return True, f"cross-source military-remains repatriation same count={count_a} within=6h"
