"""Conservative, source-grounded final-claim safeguards.

This is a deterministic high-confidence verifier, not general semantic NLI.
Only block unsupported factual certainty when the original evidence explicitly
qualifies a claim and the rewritten claim closely matches its salient words.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from .evidence_ledger import extract_source_evidence

_WORD = re.compile(r"(?iu)[а-яіїєґa-z0-9]{3,}")
_HEDGE = re.compile(r"(?iu)\b(?:попередньо|ймовірно|нібито|можливо|непідтверджен\w*|за\s+попередн\w*\s+даними|за\s+непідтверджен\w*\s+даними)\b")
_STOP = frozenset({"повідомляють", "повідомили", "попередньо", "інформація", "відомо", "даними", "можливо", "ймовірно", "нібито", "після", "через", "який", "якій", "яких", "також", "сьогодні", "наразі", "цього", "тому", "відбулося", "сталося"})
_TERMINATOR = re.compile(r"(?<=[.!?…])\s+|\n+")


@dataclass(frozen=True)
class ClaimViolation:
    code: str
    source_quote: str
    final_quote: str


def _tokens(value: str) -> set[str]:
    return {w.casefold() for w in _WORD.findall(value) if w.casefold() not in _STOP}


def verify_qualified_claims(raw_source: str, final_text: str, *, source_id: str) -> tuple[ClaimViolation, ...]:
    """Reject a certain rewrite of a distinctly uncertain source assertion.

    The detector requires >=3 shared substantive words and substantial overlap
    to avoid conflating unrelated source and output sentences.
    """
    ledger = extract_source_evidence(raw_source, source_id)
    qualified = [e for e in ledger.entries if e.uncertainty]
    if not qualified:
        return ()
    statements = [part.strip() for part in _TERMINATOR.split(str(final_text or "")) if part.strip()]
    violations: list[ClaimViolation] = []
    for line in statements:
        if _HEDGE.search(line):
            continue
        target = _tokens(line)
        if len(target) < 3:
            continue
        for evidence in qualified:
            terms = _tokens(evidence.quote)
            overlap = target & terms
            if len(overlap) >= 3 and len(overlap) / max(1, min(len(terms), len(target))) >= 0.65:
                violations.append(ClaimViolation("MONITORING_UNCERTAINTY_ESCALATION", evidence.quote, line))
                break
    return tuple(violations)
