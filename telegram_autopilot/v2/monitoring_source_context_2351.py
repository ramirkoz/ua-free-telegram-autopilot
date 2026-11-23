"""2.3.51: source-owned regional news completeness, 23 Nov LIVE regressions.

Do not repeat the donor channel's navigation/pinned-message housekeeping as
municipal service news. Do not turn a context-free casualty fragment into a
standalone war report. Rich source-owned facts, individual memorial notices,
real schedules and material updates remain eligible.

No external API, operator settings, article IDs, Telegram sends or DB writes.
"""
from __future__ import annotations

import re
from typing import Any


def _get(row: Any, key: str) -> str:
    try:
        value = row[key]
    except (KeyError, IndexError, TypeError):
        value = getattr(row, key, "")
    return str(value or "")


def _source(row: Any) -> str:
    # Title is sometimes a clipped version of the very same Telegram body.
    return (_get(row, "raw_text") or _get(row, "title")).strip()[:7000]


_SERVICE_TOPIC = re.compile(
    r"(?iu)\b(?:графік\w*|відключенн\w*|розклад\w*|"
    r"електропостачанн\w*|світл\w*)\b"
)
_DONOR_NAVIGATION = re.compile(
    r"(?iu)(?:"
    r"\bзакріплен\w*\b.{0,90}\b(?:графік\w*|розклад\w*|повідомленн\w*)\b|"
    r"\b(?:графік\w*|розклад\w*)\b.{0,100}\b(?:закріплен\w*|шапц\w*\s+канал\w*)\b|"
    r"\bу\s+шапц\w*\s+(?:наш\w*\s+)?канал\w*\b|"
    r"\b(?:в|у)\s+закріплен\w*\s+повідомленн\w*\b"
    r")"
)
# Concrete usable rows/times distinguish an actual service notice from a
# reminder that another channel has a pinned schedule. Never infer data from
# a pinned item that the operator did not ingest.
_ACTIONABLE_SCHEDULE = re.compile(
    r"(?iu)(?:\b(?:[01]?\d|2[0-3])[:.][0-5]\d\b|"
    r"\b(?:[1-6][.][1-2])\s*[:—–-]\s*\d|"
    r"\b(?:з\s+\d{1,2}\s+до\s+\d{1,2})\b)"
)
_PLURAL_CASUALTY = re.compile(
    r"(?iu)\b(?:\d+|двоє|двох|дві|троє|трьох|три|"
    r"четверо|чотири|п'ятеро|п’ятеро|п'ять|п’ять|"
    r"шестеро|шість|семеро|сім)\s+"
    r"(?:(?:люд\w*|осіб|жител\w*|мешканц\w*)\s+)?"
    r"(?:загинул\w*|загибл\w*)\b"
)
_WAR_INCIDENT = re.compile(
    r"(?iu)\b(?:атак\w*|удар\w*|обстріл\w*|пожеж\w*|влучан\w*)\b"
)
_CONCRETE_SITE = re.compile(
    r"(?iu)\b(?:будівл\w*|будин\w*|багатоповерхів\w*|"
    r"клінік\w*|лікарн\w*|госпітал\w*|школ\w*|"
    r"медичн\w*\s+центр\w*|офісн\w*\s+центр\w*|"
    r"приватн\w*\s+(?:заклад\w*|будин\w*)|"
    r"підприємств\w*|зупинк\w*|автобус\w*|автомобіл\w*)\b"
)
# Names of an authority ("Запорізька ОВА") or a publisher are NOT a place
# where the incident happened. Keep this grounded in actual incident text.
_CONCRETE_PLACE = re.compile(
    r"(?iu)\b(?:запоріжж\w*|вознесенівськ\w*|хортицьк\w*\s+район\w*|"
    r"шевченківськ\w*\s+район\w*|оріхів\w*|мелітопол\w*|"
    r"бердянськ\w*|гуляйпол\w*|полог\w*|василів\w*|"
    r"енергодар\w*|токмак\w*|дніпрорудн\w*)\b|"
    r"\b(?:у|в|біля|поблизу)\s+(?:місті|селі|селищі|громаді)\s+"
    r"[А-ЯІЇЄҐ][а-яіїєґ'’-]{3,}"
)


def monitoring_source_context_reason_2351(article: Any) -> str:
    """A narrow source-only veto, not a region/genre/keyword blacklist."""
    source = _source(article)
    if not source:
        return ""
    # #5714 / 111168: "our schedule is pinned in our channel header".
    # It contains NO new outages, time slots or usable schedule whatsoever.
    if (_SERVICE_TOPIC.search(source) and _DONOR_NAVIGATION.search(source)
            and not _ACTIONABLE_SCHEDULE.search(source)):
        return "MONITORING_DONOR_PINNED_SCHEDULE_NOT_NEWS_2351"
    # #5712 / 111129: three deaths and a fire 'on the third floor', without
    # naming which building or where it is. A regional outlet's brand/OVA is
    # not the incident location; a writer must not hallucinate the missing site.
    if (len(source) <= 420 and _PLURAL_CASUALTY.search(source)
            and _WAR_INCIDENT.search(source)
            and not _CONCRETE_SITE.search(source)
            and not _CONCRETE_PLACE.search(source)):
        return "MONITORING_ORPHAN_CASUALTY_FRAGMENT_2351"
    return ""


def monitoring_final_context_issue_2351(article: Any, text: str) -> str:
    """QA for casualties where the source has a named site but draft omits it.

    A writer may choose the location OR the concrete attacked site. An
    individual death notice is deliberately excluded from this mass-casualty
    protection to avoid suppressing respectful memorials.
    """
    source, final = _source(article), str(text or "").strip()
    if not final or not _PLURAL_CASUALTY.search(source):
        return ""
    if not _WAR_INCIDENT.search(source):
        return ""
    if not (_CONCRETE_SITE.search(source) or _CONCRETE_PLACE.search(source)):
        return ""
    if _CONCRETE_SITE.search(final) or _CONCRETE_PLACE.search(final):
        return ""
    return "MONITORING_MISSING_INCIDENT_CONTEXT_IN_FINAL_2351"


__all__ = [
    "monitoring_source_context_reason_2351",
    "monitoring_final_context_issue_2351",
]
