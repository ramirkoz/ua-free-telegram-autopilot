"""Conservative cross-source identity for short local road-incident reports.

A news publisher may paraphrase one incident and rehost the same moving video.
Different URLs and headline phrasing alone must not cause a second Telegram post.

Require an identical crossing type, an identical secondary named approach,
the same accident+congestion state and close source/publication time.
An update announcing road clearance, a new accident, or an opposite travel
direction is NOT suppressed. Media watermarks are not identity evidence.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any

_CRASH = re.compile(r"(?iu)\b(?:дтп|аварі\w*|зіткнен\w*|collision|crash)\b")
_CONGESTION = re.compile(
    r"(?iu)\b(?:затор\w*|корок|черг\w*\s+(?:авто\w*|машин\w*)|"
    r"ускладнен\w*\s+рух\w*|traffic\s+jam|congestion)\b"
)
_CROSSING = {
    "dam": re.compile(r"(?iu)\b(?:гребл\w*|дамб\w*)\b"),
    "bridge": re.compile(r"(?iu)\b(?:мост\w*|мосту|мостом|bridge)\b"),
}
_ROAD_NAME = re.compile(
    r"(?iu)\b(?:кільц\w*|вул(?:\.|иц\w*)|проспект\w*|перехрест\w*)"
    r"\s+(?:(?:на|по)\s+)?(?:вул(?:\.|иц\w*)\s+)?"
    r"(?P<name>[а-яіїєґ'’\-]{6,})\b"
)
_ROAD_NAME_NOISE = {"дорозі", "дороги", "кільці", "вулиці", "вулиця", "місті",
                    "напрямку", "перехресті"}
_SEPARATE = re.compile(
    r"(?iu)\b(?:ще\s+одн\w*\s+(?:дтп|аварі\w*)|"
    r"інш\w*\s+(?:дтп|аварі\w*)|"
    r"нова\s+(?:дтп|аварія)|друга\s+(?:дтп|аварія))\b"
)
_CLEARED = re.compile(
    r"(?iu)(?:рух\s+(?:відновил\w*|відкрили|відкрито|розблокувал\w*)|"
    r"дорог\w*\s+(?:відкрили|розблокувал\w*)|"
    r"затор\s+(?:зник|розсмоктався|ліквідовано)|"
    r"проїзд\s+(?:відновил\w*|відкрили))"
)
_TO_LEFT = re.compile(
    r"(?iu)(?:з\s+правого\s+на\s+лівий|"
    r"(?:у|в)\s+напрямку\s+лівого\s+берег\w*|"
    r"в\s+бік\s+лівого\s+берег\w*)"
)
_TO_RIGHT = re.compile(
    r"(?iu)(?:з\s+лівого\s+на\s+правий|"
    r"(?:у|в)\s+напрямку\s+правого\s+берег\w*|"
    r"в\s+бік\s+правого\s+берег\w*)"
)


def _v(row: Any, key: str) -> str:
    try:
        value = row[key]
    except (KeyError, TypeError, IndexError):
        value = getattr(row, key, "")
    return str(value or "")


def _source_body(row: Any) -> str:
    # Text from the source has priority: generated final captions should never
    # be allowed to invent place or event identity.
    return (_v(row, "title") + "\n" + _v(row, "raw_text"))[:4000].casefold()


def _crossings(text: str) -> set[str]:
    return {name for name, pattern in _CROSSING.items() if pattern.search(text)}


def _approach_names(text: str) -> set[str]:
    names: set[str] = set()
    for match in _ROAD_NAME.finditer(text):
        name = match.group("name").strip("-'’")
        if name in _ROAD_NAME_NOISE or len(name) < 7:
            continue
        # Handles Каховській/Каховська; a shared named approach is required.
        names.add(name[:7])
    return names


def _time(row: Any) -> datetime | None:
    for key in ("source_published_at", "published_at", "discovered_at"):
        raw = _v(row, key).strip()
        if not raw:
            continue
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def _direction(text: str) -> str:
    left = bool(_TO_LEFT.search(text))
    right = bool(_TO_RIGHT.search(text))
    if left == right:
        return ""
    return "left" if left else "right"


def traffic_incident_same_event(current: Any, candidate: Any) -> tuple[bool, str]:
    """High-precision traffic incident lane, for both pre-AI and prepublish.

    Generic accident/congestion phrases alone are never enough. The pair must
    share a crossing AND a named road approach within two hours, no distinct
    incident/update indicators, and no explicitly conflicting directions.
    """
    source_a = _v(current, "source_id")
    source_b = _v(candidate, "source_id")
    if source_a and source_b and source_a == source_b:
        return False, "same publisher rows require exact-identity lane"

    a, b = _source_body(current), _source_body(candidate)
    if not (_CRASH.search(a) and _CRASH.search(b)
            and _CONGESTION.search(a) and _CONGESTION.search(b)):
        return False, "not a matching accident+congestion pair"

    crossings = _crossings(a) & _crossings(b)
    approaches = _approach_names(a) & _approach_names(b)
    if not crossings or not approaches:
        return False, "no corroborated crossing and named road approach"

    if _SEPARATE.search(a) or _SEPARATE.search(b):
        return False, "explicit separate accident"
    if _CLEARED.search(a) or _CLEARED.search(b):
        return False, "material traffic clearance update"

    da, db = _direction(a), _direction(b)
    if da and db and da != db:
        return False, "opposite travel directions"

    ta, tb = _time(current), _time(candidate)
    if ta is None or tb is None:
        return False, "event times unavailable"
    if abs((ta - tb).total_seconds()) > 2 * 3600:
        return False, "outside two-hour local-incident window"

    return True, ("cross-source traffic event crossing=" +
                  ",".join(sorted(crossings)) + " approach=" +
                  ",".join(sorted(approaches)) + " within=2h")
