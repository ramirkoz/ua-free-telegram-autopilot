"""Narrow Ukrainian multi-athlete digest identity for monitoring channels.

A published Zaporizhzhia medal digest is not a new event merely because the
second source lists fewer athletes and different coach details. Require three
independent PERSON names, two sports and two countries, with contemporaneous
source timestamps. This does NOT merge different competitions or updates.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any


_NAME = re.compile(
    r"(?u)\b[А-ЯІЇЄҐ][а-яіїєґ’'-]{2,}\s+[А-ЯІЇЄҐ][а-яіїєґ’'-]{2,}\b"
)
_SPORTS = {
    "тхеквондо": re.compile(r"(?iu)тхеквонд"),
    "шашки": re.compile(r"(?iu)шашк"),
    "веслування": re.compile(r"(?iu)веслуван|байдарк|каное"),
    "таїландський бокс": re.compile(r"(?iu)таїландськ|тайськ"),
    "акробатичний рок-н-рол": re.compile(r"(?iu)акробат|рок-н-рол"),
}
_COUNTRIES = {
    "катар": re.compile(r"(?iu)катар|дос[іа]\b"),
    "нідерланди": re.compile(r"(?iu)нідерланд"),
    "аргентина": re.compile(r"(?iu)аргентин"),
    "франція": re.compile(r"(?iu)франц"),
    "польща": re.compile(r"(?iu)польщ"),
}
_STOP_NAMES = frozenset({
    "представники запорізької", "представник запорізької",
    "вихованка запорізької", "чемпіоната європи", "чемпіонату європи",
    "від аргентини", "україни сергій", "формейшн дівчата",
})


def _read(row: Any, key: str) -> str:
    try:
        return str(row[key] or "")
    except (TypeError, KeyError, IndexError):
        return str(getattr(row, key, "") or "")


def _tags(value: str, patterns: dict[str, re.Pattern]) -> set[str]:
    return {name for name, pattern in patterns.items() if pattern.search(value)}


def sports_medal_same_event(current: Any, candidate: Any) -> tuple[bool, str]:
    left = _read(current, "raw_text")[:12000]
    right = _read(candidate, "raw_text")[:12000]
    if not left or not right:
        return False, ""
    for text in (left, right):
        if not re.search(r"(?iu)запоріж|запоріз", text):
            return False, ""
        if not re.search(r"(?iu)спортсмен|чемпіонат|змаганн|турнір", text):
            return False, ""
        if not re.search(r"(?iu)срібл|бронз|золот|медал|нагород", text):
            return False, ""
    try:
        a = datetime.fromisoformat(_read(current, "source_published_at"))
        b = datetime.fromisoformat(_read(candidate, "source_published_at"))
        if a.tzinfo is None or b.tzinfo is None:
            return False, ""
        if abs((a - b).total_seconds()) > 36 * 3600:
            return False, ""
    except (ValueError, TypeError, OverflowError):
        return False, ""

    names_a = {m.casefold() for m in _NAME.findall(left)} - _STOP_NAMES
    names_b = {m.casefold() for m in _NAME.findall(right)} - _STOP_NAMES
    shared_names = names_a & names_b
    shared_sports = _tags(left, _SPORTS) & _tags(right, _SPORTS)
    shared_countries = _tags(left, _COUNTRIES) & _tags(right, _COUNTRIES)

    if len(shared_names) < 3 or len(shared_sports) < 2 or len(shared_countries) < 2:
        return False, ""
    return True, (
        "same Zaporizhzhia multi-athlete medal digest: "
        + ", ".join(sorted(shared_names)[:4])
        + "; sports=" + ",".join(sorted(shared_sports))
        + "; countries=" + ",".join(sorted(shared_countries))
    )
