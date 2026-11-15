"""2.3.33: original-source *mission milestone* equivalence, not brand dedupe.

A flight is identified by its named vehicle and test-flight number, and by a
specific completed operation on a specified stage. Distinct tests, lower-stage
recoveries, investigations, and verified later missions remain separate. This
code neither reads nor writes the operator store and is used at ingest and at
READY->Telegram against the published ledger.
"""
from __future__ import annotations

import re
from typing import Any


def _get(row: Any, key: str) -> str:
    try:
        return str(row[key] or "")
    except (KeyError, IndexError, TypeError):
        return str(getattr(row, key, "") or "")


_VEHICLE = re.compile(r"\b(starship|falcon\s*9|new\s+glenn|ariane\s*6)\b", re.I)
_MISSION_NUM = re.compile(r"\b(?:flight|mission|test(?:\s+flight)?|пол[іе]т|випробувальн\w*\s+пол[іе]т)\s*(?:no\.?\s*)?[#№]?\s*(\d{1,3})(?:st|nd|rd|th)?\b", re.I)
_ORDINAL_TEST = re.compile(r"\b(\d{1,3})(?:st|nd|rd|th)\s+(?:test\s+)?flight\b", re.I)
_STAGE = re.compile(r"(?:\b(?:upper|top|second)\s+(?:stage|part|section)\b|"
                    r"\bship\s+upper\s+stage\b|\bstarship\s+(?:vehicle\s+itself|itself)\b|"
                    r"\b(?:верхн\w*\s+(?:ступ[іе]н\w*|частин\w*)|корабель\s+ship)\b)", re.I)
_CATCH = re.compile(r"(?:\b(?:catch|caught|captur(?:e|ed)|chopstick|mechazilla)\b|"
                    r"\breturn(?:s|ed)?\s+(?:to\s+(?:the\s+)?)?(?:launch\s+(?:pad|tower)|tower)\b|"
                    r"\b(?:спіймал\w*|перехоп\w*|повернул\w*\s+(?:до|на)\s+(?:веж|старт))\b)", re.I)
_TOWER = re.compile(r"(?:\b(?:launch\s+(?:pad|tower)|tower|mechazilla|chopstick)\b|"
                    r"\b(?:веж\w*|механічн\w*\s+рук\w*)\b)", re.I)
_COMPLETED = re.compile(r"(?:\b(?:first|successfully|epic|historic|returns?|returned|caught|captured|victory)\b|"
                        r"\b(?:уперше|вперше|успішн\w*|повернул\w*|спіймал\w*)\b)", re.I)
_PREVIEW = re.compile(r"\b(?:plans?|planning|will\s+try|may\s+attempt|could\s+attempt|"
                      r"to\s+try|preview|upcoming|before\s+launch|планує|плануван\w*)\b", re.I)
_NEW_RESULT = re.compile(r"\b(?:new\s+(?:investigation|failure\s+analysis|findings|cause|evidence)|"
                         r"cause\s+of\s+failure|official\s+correction|confirmed\s+correction|"
                         r"нов\w*\s+(?:результат\w*|виснов\w*|розсл\w*)|"
                         r"виправлен\w*\s+дан\w*)\b", re.I)
_BOOSTER_TITLE = re.compile(r"\b(?:booster|super\s+heavy|прискорювач\w*)\b", re.I)
_UPPER_TITLE = re.compile(r"\b(?:upper\s+stage|top\s+part|ship\s+upper|starship\s+returns?|"
                         r"catch\s+of\s+starship|starship\s+catch|chopstick.*starship|"
                         r"верхн\w*\s+(?:ступ[іе]н\w*|частин\w*))\b", re.I)


def mission_milestone_key_2333(row: Any) -> str:
    """Non-empty only when source independently establishes a *completed* milestone."""
    title = _get(row, "title")[:550]
    body = _get(row, "raw_text")[:1900]
    if not title or not body:
        return ""
    text = title + "\n" + body
    vehicle = _VEHICLE.search(title)
    if not vehicle:
        return ""
    # This is *not* any SpaceX topic: require one concrete flight number.
    number_match = _MISSION_NUM.search(text) or _ORDINAL_TEST.search(text)
    if not number_match:
        return ""
    num = int(number_match.group(1))
    if not _CATCH.search(title) or not _TOWER.search(text) or not _STAGE.search(text):
        return ""
    if not _COMPLETED.search(text[:1000]):
        return ""
    if _NEW_RESULT.search(title):
        return ""
    # A separate *booster* milestone should not be merged with an upper-stage
    # catch merely because the full article also reviews the upper stage.
    if _BOOSTER_TITLE.search(title) and not _UPPER_TITLE.search(title):
        return ""
    # An article solely previewing a planned operation is not a completed
    # milestone. Do not interpret 'planned double catch' in a completed report
    # as preview when the headline reports an actual catch.
    if _PREVIEW.search(title) and not _COMPLETED.search(title):
        return ""
    return f"rocket:{vehicle.group(1).casefold().replace(' ', '')}:flight:{num}:upper-stage-tower-catch"


def mission_milestone_same_event_2333(current: Any, candidate: Any) -> tuple[bool, str]:
    first = mission_milestone_key_2333(current)
    second = mission_milestone_key_2333(candidate)
    if first and first == second:
        return True, f"2.3.33 same completed mission milestone {first} (cross-source / video recaps included)"
    return False, "distinct or insufficiently evidenced mission milestone"
