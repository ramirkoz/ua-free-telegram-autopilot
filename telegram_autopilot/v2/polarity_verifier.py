"""High-confidence polarity preservation checks for monitoring copy.

This is a narrow safety layer. It is NOT complete semantic entailment.
Only compare statements that share a distinctive quoted source anchor;
uncertain or unaligned pairs are not automatically treated as false.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .evidence_ledger import extract_source_evidence

_SPLIT = re.compile(r"(?<=[.!?…])\s+|\n+")
_NEGATION = re.compile(r"(?iu)\b(?:не|немає|нема|відсутн\w*|жодн\w*|без)\b")
_ADDITIVE = re.compile(r"(?iu)\bне\s+(?:лише|тільки|просто)\b")

def _has_negation(value: str) -> bool:
    return bool(_NEGATION.search(_ADDITIVE.sub("", value)))


def _negated_anchor(value: str, overlap: set[str]) -> bool:
    # The negation must belong to the aligned claim, not a second clause
    # joined to it in a source or summary. The first content words after
    # the marker form the conservative, lexical scope of that marker.
    value = _ADDITIVE.sub("", value)
    for match in _NEGATION.finditer(value):
        tail = re.split(r"[,;.!?…]|\b(?:але|однак|а\s+також|чи)\b", value[match.end():], maxsplit=1, flags=re.I)[0]
        words = [m.group(0).casefold() for m in _ATOM.finditer(tail)
                 if m.group(0).casefold() not in _IGNORE][:2]
        if not words or overlap.intersection(words):
            return True
    return False

_ATOM = re.compile(r"(?iu)[а-яіїєґa-z0-9]{4,}")
_IGNORE = frozenset({"повідомляють", "інформація", "сьогодні", "наразі", "повідомили", "попередньо", "відбулося", "становить", "сталося", "цього", "через", "після", "однак", "також", "яких", "який", "якій", "немає", "відсутня", "відсутні"})


@dataclass(frozen=True)
class PolarityViolation:
    code: str
    source_quote: str
    final_quote: str


def _terms(value: str) -> set[str]:
    return {m.group(0).casefold() for m in _ATOM.finditer(value) if m.group(0).casefold() not in _IGNORE}


def verify_source_polarity(source_text: str, final_text: str, *, source_id: str) -> tuple[PolarityViolation, ...]:
    ledger = extract_source_evidence(source_text, source_id)
    output = [x.strip() for x in _SPLIT.split(str(final_text or "")) if x.strip()]
    findings: list[PolarityViolation] = []
    for statement in output:
        tokens = _terms(statement)
        if len(tokens) < 3:
            continue
        candidates = []
        for source in ledger.entries:
            original_terms = _terms(source.quote)
            overlap = original_terms & tokens
            if len(overlap) < 3:
                continue
            similarity = len(overlap) / max(1, min(len(original_terms), len(tokens)))
            if similarity >= 0.75:
                candidates.append(source)
        # Fail closed on semantic ambiguity rather than declaring a match:
        # an output assertion matching several source statements cannot safely
        # be compared to one selected fragment.
        if len(candidates) != 1:
            continue
        original = candidates[0]
        if _has_negation(original.quote) != _has_negation(statement):
            negated = original.quote if _has_negation(original.quote) else statement
            if not _negated_anchor(negated, _terms(original.quote) & tokens):
                continue
            findings.append(PolarityViolation(
                "MONITORING_SOURCE_POLARITY_FLIP", original.quote, statement
            ))
    return tuple(findings)
