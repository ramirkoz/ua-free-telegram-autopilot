"""2.3.16: observed, conservative post-final language and topic gates.

Not a semantic fact checker. It rejects a small set of attested corruptions
and unrelated weather sentences mixed into an explicitly cultural local item.
All source/Fact/Media and publishing checks remain independent.
"""
from __future__ import annotations

import re
from typing import Any

_ATTESTED = (
    (re.compile(r"(?iu)\bпершопрестолов\w*\b"), "UA_2316_PERSHOPRESTOLOVE"),
    (re.compile(r"(?iu)\bлакомств\w*\b"), "UA_2316_LAKOMSTVA"),
)
_LOWER_SENTENCE = re.compile(r"[.!?…][ \t\r\n]+([а-яіїєґ])")
_CULTURAL_TITLE = re.compile(
    r"(?iu)(?:палац\w*\s+культур\w*|музе[йюя]|виставк\w*|"
    r"сторічч\w*|річниц\w*|культурн\w*\s+поді\w*|"
    r"anniversary|centenary|museum|exhibition)"
)
_WEATHER_TAIL = re.compile(
    r"(?iu)(?:^|\n|[.!?]\s+)(?:за\s+прогнозом\s+синоптик\w*|"
    r"прогноз\s+погод\w*|синоптик\w*\s+(?:прогнозу\w*|повідом\w*)|"
    r"(?:завтра|сьогодні)\s+(?:очікуєтьс\w*|буде)\s+"
    r"(?:дощ|сніг|сонячн|хмарн))"
)


def _field(row: Any, field: str) -> str:
    try:
        return str(row[field] or "")
    except (KeyError, TypeError, IndexError):
        return str(getattr(row, field, "") or "")


def post_language_issues_2316(text: str) -> tuple[str, ...]:
    value = str(text or "")
    issues = [code for pattern, code in _ATTESTED if pattern.search(value)]
    # A full stop followed by a lowercase Ukrainian letter is not a legal
    # sentence boundary. Ignore URLs and list bullets to reduce false flags.
    visible = re.sub(r"https?://\S+|\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", " ", value)
    if _LOWER_SENTENCE.search(visible):
        issues.append("UA_2316_LOWERCASE_SENTENCE_START")
    return tuple(dict.fromkeys(issues))


def mixed_topic_issues_2316(article: Any, final_text: str) -> tuple[str, ...]:
    """Catch culture story with an unrelated standalone weather forecast."""
    title = _field(article, "title")
    final = str(final_text or "")
    if not (_CULTURAL_TITLE.search(title) and _WEATHER_TAIL.search(final)):
        return ()
    # Weather as the actual headline would be a different editorial story.
    if re.search(r"(?iu)\b(?:погод\w*|синоптик\w*|прогноз\w*)\b", title):
        return ()
    return ("EDITORIAL_2316_UNRELATED_WEATHER_TAIL",)
