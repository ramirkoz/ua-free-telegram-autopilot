"""Utility service updates: outage schedules and supply interruptions.

A power/water/gas/heat schedule is a fact residents act on, whoever relays it
and however tersely it is written ("Черга 1.1 з 06:30 до 10:30 ..."). Two older
gates lost such posts although the operator marks them as wanted:

* the forward veto (a community forwarding the operator's schedule), and
* the two-sentence source floor (a schedule is a list, not prose).

This module only RECOGNISES such a post from its own source text. It never
relaxes rumour, announcement, fact or duplicate gates; the same schedule relayed
by many communities is still collapsed by the event dedupe.
"""
from __future__ import annotations

import re
from typing import Any

_UTILITY = re.compile(
    r"(?iu)(?:\bгпв\b|\bгав\b|графік\w*\s+(?:погодинн\w+\s+)?(?:відключен\w+|подач\w+)|"
    r"(?:погодинн\w+|аварійн\w+|стабілізаційн\w+)\s+відключен\w+|"
    r"відключен\w+\s+(?:світла|електро\w+|води|газу|тепла|опалення)|знеструмлен\w+|"
    r"без\s+(?:світла|електро\w+|води|водопостачання|газу|тепла|опалення)|"
    r"(?:водо|газо|тепло|електро)постачанн\w+|\bукренерго\b|\w*обленерго\b|водоканал\w*|тепломереж\w*)"
)
_QUEUE = re.compile(r"(?iu)\bчерг\w*\s*\d(?:\.\d)?|\b\d\.\d\s*[:\-–—]")
_TIME_RANGE = re.compile(r"\b\d{1,2}[:.]\d{2}\s*(?:до|по|[-–—])\s*\d{1,2}[:.]\d{2}")
_RUMOUR = re.compile(r"(?iu)\b(?:кажуть|подейкують|пишуть\s+у\s+соцмережах|за\s+чутками|нібито|ймовірно\s+будуть)\b")


def _v(row: Any, key: str) -> str:
    try:
        return str(row[key] or "")
    except (KeyError, IndexError, TypeError):
        return str(getattr(row, key, "") or "")


def _text(article: Any) -> str:
    title, body = _v(article, "title"), _v(article, "raw_text")
    return body if title and title in body else f"{title}\n{body}"


def utility_service_update(article: Any) -> bool:
    """True for a concrete utility schedule/outage update (not a rumour)."""
    text = _text(article)
    if not _UTILITY.search(text) or _RUMOUR.search(text):
        return False
    return bool(_TIME_RANGE.search(text) or _QUEUE.search(text) or re.search(r"\b\d{1,2}[.]\d{2}[.]\d{2,4}\b|\b\d{1,2}\s+(?:січня|лютого|березня|квітня|травня|червня|липня|серпня|вересня|жовтня|листопада|грудня)\b", text))


def structured_schedule(article: Any) -> bool:
    """True when a utility update carries its facts as a time table, not prose."""
    text = _text(article)
    return utility_service_update(article) and len(_TIME_RANGE.findall(text)) >= 2
