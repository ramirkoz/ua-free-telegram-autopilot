"""2.3.6: multi-athlete Zaporizhzhia medal digest cross-source identity.

Require three shared Cyrillic full names, two countries, two sports, and a
bounded time window. Generic medal mentions cannot cause duplicate vetoes.
"""
from __future__ import annotations
from datetime import datetime
import re
from typing import Any

_PERSON = re.compile(r"(?u)\b[А-ЯІЇЄҐ][а-яіїєґ’'-]{2,}\s+[А-ЯІЇЄҐ][а-яіїєґ’'-]{2,}\b")
_SPORTS = {
    "taekwondo": re.compile(r"(?iu)тхеквонд"),
    "checkers": re.compile(r"(?iu)шаш(?:к|ок)"),
    "rowing": re.compile(r"(?iu)веслуван|байдарк|каное"),
    "thai_boxing": re.compile(r"(?iu)таїландськ|тайськ\s+бокс"),
    "rock_and_roll": re.compile(r"(?iu)акробатичн.{0,16}рок-н-рол"),
}
_COUNTRIES = {
    "qatar": re.compile(r"(?iu)катар|дос[іа]\b"),
    "netherlands": re.compile(r"(?iu)нідерланд"),
    "argentina": re.compile(r"(?iu)аргентин"),
    "france": re.compile(r"(?iu)франц"),
    "poland": re.compile(r"(?iu)польщ"),
}


def _read(article: Any, key: str) -> str:
    try:
        return str(article[key] or "")
    except (KeyError, IndexError, TypeError):
        return str(getattr(article, key, "") or "")


def _hits(text: str, patterns: dict) -> set[str]:
    return {name for name, regex in patterns.items() if regex.search(text)}


def sports_medal_same_event_236(current: Any, prior: Any) -> tuple[bool, str]:
    left, right = (_read(current, "raw_text")[:11000], _read(prior, "raw_text")[:11000])
    if not left or not right:
        return False, ""
    for s in (left, right):
        if not re.search(r"(?iu)запоріж|запоріз", s):
            return False, ""
        if not re.search(r"(?iu)спортсмен|чемпіонат|турнір|змаганн", s):
            return False, ""
        if not re.search(r"(?iu)срібл|бронз|золот|медал|нагород|призер", s):
            return False, ""
    try:
        a, b = (datetime.fromisoformat(_read(item, "source_published_at").replace("Z", "+00:00")) for item in (current, prior))
        if a.tzinfo is None or b.tzinfo is None or abs((a - b).total_seconds()) > 36 * 3600:
            return False, ""
    except (ValueError, TypeError, OverflowError):
        return False, ""
    common_people = {v.casefold() for v in _PERSON.findall(left)} & {v.casefold() for v in _PERSON.findall(right)}
    common_sports = _hits(left, _SPORTS) & _hits(right, _SPORTS)
    common_countries = _hits(left, _COUNTRIES) & _hits(right, _COUNTRIES)
    if len(common_people) < 3 or len(common_sports) < 2 or len(common_countries) < 2:
        return False, ""
    return True, ("SAME_MEDAL_DIGEST_236: " + ",".join(sorted(common_people)[:5])
                  + "; sports=" + ",".join(sorted(common_sports))
                  + "; countries=" + ",".join(sorted(common_countries)))
