"""2.3.43 owner LIVE RED: non-news procedural teardown is not CTRL+UA news.

Source text only; no provider calls. Do not turn repairability into a banned topic:
verified product design changes, safety recalls, law, formal repairability scores
and user-facing consequences remain eligible to the normal editorial review.
"""
from __future__ import annotations
import re
from typing import Any


def _value(row: Any, key: str) -> str:
    try:
        return str(row[key] or "")
    except (KeyError, TypeError, IndexError):
        return str(getattr(row, key, "") or "")


_REPAIR_HEADLINE = re.compile(
    r"(?iu)\b(?:tear[ -]?down|disassembl\w*|repairability|repairs?|repairing|"
    r"difficult\s+to\s+repair|right[ -]to[ -]repair)\b"
)
_PROCEDURAL_TERMS = (
    r"\bconnectors?\b", r"\bmainboard\b", r"\bthermal\s+compound\b",
    r"\b(?:glue|glued|adhesive)\b", r"\bscrews?\b", r"\bpry(?:ing)?\b",
    r"\bunplug(?:ging)?\b", r"\b(?:subwoofer|speaker\s+modules?)\b",
    r"\b(?:display\s+removal|remove\s+the\s+display)\b",
    r"\b(?:ipa|solvents?)\b", r"\bdisassembly\b",
)
# Concrete, source-confirmed public outcomes; NOT bare speculation such as
# 'may run afoul of regulations' or 'might get a low score'.
_CONSUMER_OUTCOME = re.compile(
    r"(?iu)(?:\b(?:formal|official|published|awarded)\s+repairability\s+score\b|"
    r"\brepairability\s+score\s+(?:of\s+)?\d{1,2}\s*(?:/|out\s+of)\s*10\b|"
    r"\b(?:recalls?|recalled)\s+(?:the\s+)?(?:device|product|model|battery)\b|"
    r"\b(?:regulator|court|commission)\s+(?:ordered|ruled|fined|banned)\b|"
    r"\b(?:new|redesigned|replaceable|modular|user[ -]replaceable)\s+(?:battery|"
    r"screen|port|connector|design|module)\b|"
    r"\b(?:warranty|repair\s+program)\s+(?:extended|expanded|announced)\b)"
)


def science_procedural_teardown_reason_2343(article: Any) -> str:
    """Owner's #2060: a narrowly procedural recap with no material new outcome."""
    title = _value(article, "title")[:900]
    body = _value(article, "raw_text")[:7500]
    if not (_REPAIR_HEADLINE.search(title) and body):
        return ""
    if not re.search(r"(?iu)\b(?:ifixit|tear[ -]?down|disassembl\w*)\b", body):
        return ""
    if _CONSUMER_OUTCOME.search(title + "\n" + body):
        return ""
    procedure_signals = sum(bool(re.search(pattern, body, re.I)) for pattern in _PROCEDURAL_TERMS)
    if procedure_signals < 4:
        return ""
    return "SCIENCE_TEARDOWN_PROCEDURE_NO_READER_NEWS_2343"
