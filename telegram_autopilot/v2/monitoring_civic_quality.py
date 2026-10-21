"""Channel-scoped fail-closed civic relevance checks for opted-in monitoring feeds.

These checks use the *original source* and complement the model's classification.
They deliberately do not infer or publish battlefield coordinates.
"""
from __future__ import annotations

import re
from typing import Any

from .domain import ChannelMode

_CYR = re.I
_FORCE = re.compile(r"(?iu)\b(?:росіян\w*|російськ\w*|ворог\w*|окупант\w*|військ\w*|армі\w*|сил\w*\s+рф)\b")
_ADVANCE = re.compile(r"(?iu)\b(?:просува\w*|просун\w*|просуван\w*|наступ\w*|відступ\w*|відход\w*|захоп\w*|зайнял\w*\s+позиці\w*|контрол\w*\s+над)\b")
_PLACES = re.compile(r"(?iu)\b(?:напрям\w*|поблизу|біля|села|село|населен\w*\s+пункт\w*|позиці\w*|ділянц\w*|фронт\w*|област\w*|район\w*|карт\w*|територі\w*)\b")
_GENERIC_VACANCY = re.compile(r"(?iu)\b(?:актуальн\w*\s+вакансі\w*|підбірк\w*\s+вакансі\w*|вакансі\w*\s+(?:для|у|в)\s+впо|опублікувал\w*[^.!?\n]{0,100}\bвакансі\w*)")
_LOSS_ROUNDUP = re.compile(r"(?iu)\b(?:жмурк\w*|двохсот\w*|двухсот\w*|втрат\w*\s+серед\s+(?:російськ\w*\s+)?військов\w*|ліквідован\w*\s+окупант\w*)\b")
_CIVILIAN = re.compile(r"(?iu)\b(?:цивільн\w*|мирн\w*\s+жител\w*|пошкоджен\w*\s+будин\w*|житлов\w*\s+будин\w*|рятувальник\w*|постраждал\w*\s+мешканц\w*)\b")


def _value(row: Any, key: str) -> str:
    try:
        value = row[key]
    except (KeyError, TypeError, IndexError):
        value = getattr(row, key, "")
    return str(value or "")


def civic_relevance_exclusion(channel: Any, article: Any) -> str:
    """Fail closed only for a channel that has explicitly opted into the live gate."""
    if channel.mode != ChannelMode.MONITORING:
        return ""
    if "[LIVE_NOW_RC96]" not in str(channel.policy.rejection_rules or ""):
        return ""
    original = (_value(article, "title") + "\n" + _value(article, "raw_text"))[:8000]
    if _FORCE.search(original) and _ADVANCE.search(original) and _PLACES.search(original):
        return "MONITORING_TACTICAL_UPDATE: поточні зміни бойових позицій/наступу не є цивільною завершеною подією"
    if _GENERIC_VACANCY.search(original):
        return "MONITORING_OFF_TOPIC: загальна добірка вакансій без конкретної місцевої події"
    if _LOSS_ROUNDUP.search(original) and not _CIVILIAN.search(original):
        return "MONITORING_OFF_TOPIC: військові втрати/непідтверджена бойова хроніка без цивільного підсумку"
    return ""
