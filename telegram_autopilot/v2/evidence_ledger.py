"""Evidence provenance ledger for source claims.

Every record points to exact characters of the original source. This module
does not imply that extracted claims are independently verified; it preserves
what a source actually said so later model-backed entailment can be audited.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_TERMINATORS = re.compile(r"(?<=[.!?…])\s+|\n+")
_UNCERTAINTY = re.compile(r"(?iu)\b(?:нібито|ймовірно|попередньо|можливо|припуска\w*|за\s+непідтверджен\w*)\b")
_TIME_CURRENT = re.compile(r"(?iu)\b(?:зараз|наразі|прямо\s+зараз|у\s+ці\s+хвилини|сьогодні)\b")


@dataclass(frozen=True)
class SourceEvidence:
    source_id: str
    start: int
    end: int
    quote: str
    uncertainty: bool
    current_time_reference: bool


@dataclass(frozen=True)
class EvidenceLedger:
    source_id: str
    entries: tuple[SourceEvidence, ...]

    def source_spans_valid(self, original: str) -> bool:
        return all(
            0 <= e.start < e.end <= len(original)
            and original[e.start:e.end] == e.quote
            and e.source_id == self.source_id
            for e in self.entries
        )


def extract_source_evidence(original: str, source_id: str) -> EvidenceLedger:
    text = str(original or "")
    identifier = str(source_id or "").strip()
    if not identifier:
        raise ValueError("source_id required for traceable evidence")
    entries: list[SourceEvidence] = []
    cursor = 0
    for boundary in _TERMINATORS.finditer(text):
        _add_span(text, identifier, cursor, boundary.start(), entries)
        cursor = boundary.end()
    _add_span(text, identifier, cursor, len(text), entries)
    return EvidenceLedger(identifier, tuple(entries))


def _add_span(text: str, source_id: str, start: int, end: int,
              out: list[SourceEvidence]) -> None:
    fragment = text[start:end]
    stripped = fragment.strip()
    if not stripped:
        return
    left = len(fragment) - len(fragment.lstrip())
    right = len(fragment.rstrip())
    begin, finish = start + left, start + right
    out.append(SourceEvidence(
        source_id, begin, finish, text[begin:finish],
        bool(_UNCERTAINTY.search(stripped)),
        bool(_TIME_CURRENT.search(stripped)),
    ))
