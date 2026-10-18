"""Trace final monitoring statements to source spans.

Unmatched rewrites are diagnostic-only until measured against an operator
golden corpus: lexical similarity cannot prove factual entailment.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from .evidence_ledger import extract_source_evidence

_SENTENCE = re.compile(r"(?<=[.!?…])\s+|\n+")
_TOKEN = re.compile(r"(?iu)[a-zа-яіїєґ0-9]{4,}")
_STOP = frozenset({
    "сьогодні", "наразі", "сталося", "відбулося", "повідомив", "повідомила",
    "повідомили", "повідомляють", "відомо", "інформація", "також",
    "після", "через", "цього", "який", "яких", "якою", "відповідно",
    "йдеться", "місцеві", "джерело", "внаслідок",
})


@dataclass(frozen=True)
class StatementTrace:
    text: str
    source_start: int | None
    source_end: int | None
    source_quote: str
    lexical_overlap: float
    status: str  # EXACT, ALIGNED, UNRESOLVED


@dataclass(frozen=True)
class ClaimTraceReport:
    source_id: str
    statements: tuple[StatementTrace, ...]

    @property
    def unresolved(self) -> tuple[StatementTrace, ...]:
        return tuple(s for s in self.statements if s.status == "UNRESOLVED")


def _tokens(text: str) -> set[str]:
    return {
        match.group(0).casefold()
        for match in _TOKEN.finditer(text)
        if match.group(0).casefold() not in _STOP
    }


def trace_output_claims(source: str, output: str, *, source_id: str) -> ClaimTraceReport:
    ledger = extract_source_evidence(source, source_id)
    items: list[StatementTrace] = []
    for statement in _SENTENCE.split(str(output or "")):
        statement = statement.strip()
        if not statement:
            continue
        if statement in source:
            start = source.find(statement)
            items.append(StatementTrace(
                statement, start, start + len(statement), statement, 1.0, "EXACT"
            ))
            continue
        target = _tokens(statement)
        best = None
        best_score = 0.0
        for evidence in ledger.entries:
            matching = len(target & _tokens(evidence.quote))
            score = matching / max(1, len(target)) if target else 0.0
            if score > best_score:
                best, best_score = evidence, score
        if best is not None and len(target & _tokens(best.quote)) >= 2 and best_score >= 0.6:
            items.append(StatementTrace(
                statement, best.start, best.end, best.quote, round(best_score, 4), "ALIGNED"
            ))
        else:
            items.append(StatementTrace(statement, None, None, "", round(best_score, 4), "UNRESOLVED"))
    return ClaimTraceReport(source_id, tuple(items))
