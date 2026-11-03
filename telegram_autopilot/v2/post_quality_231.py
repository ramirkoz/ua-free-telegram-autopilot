"""2.3.1 high-confidence, operator-attested Ukrainian and source-fact QA.

These deterministic guards are intentionally narrow: reject or request a new
source-grounded final edit; NEVER rewrite source facts or Telegram messages.
"""
from __future__ import annotations

import re
from typing import Any

_BAD_UKRAINIAN = (
    (re.compile(r"(?iu)\b(?:груз|груза|грузом|грузу)\b"), "UK_RUSSIANISM_GRUZ_231"),
    (re.compile(r"(?iu)\bвуглеволокним\b"), "UK_CORRUPT_FIBER_231"),
    (re.compile(r"(?iu)\bпапер\b"), "UK_PAPER_TYPO_231"),
    (re.compile(r"(?iu)\bдо\s+шагу\b"), "UK_RUSSIANISM_STEP_231"),
    (re.compile(r"(?iu)\bдвох\s*[-–—]\s*три\s+секунди\b"), "UK_NUMERAL_AGREEMENT_SECONDS_231"),
    (re.compile(r"(?iu)\b\d{1,2}\s*[-–—]\s*\d{1,2}\s+рік\b"), "UK_AGE_PLURAL_YEARS_231"),
    (re.compile(r"(?iu)\bпо\s+\d+\s+містам\s+і\s+селах\b"), "UK_LOCATION_CASE_231"),
)


def ukrainian_operator_issues_231(text: str) -> tuple[str, ...]:
    value = str(text or "")
    return tuple(code for pattern, code in _BAD_UKRAINIAN if pattern.search(value))


def _read(article: Any, field: str) -> str:
    try:
        value = article[field]
    except (KeyError, IndexError, TypeError):
        value = getattr(article, field, "")
    return str(value or "")


# Narrow, source-provable action reversal: capsule itself splashed down with
# its cargo aboard; no claim the capsule dropped/jettisoned the cargo.
_SPLASHED = re.compile(r"(?iu)\b(?:splash(?:ed|down)?|приводнил\w*)\b")
_CAPSULE = re.compile(r"(?iu)\b(?:capsule|капсул\w*)\b")
_CARGO = re.compile(r"(?iu)\b(?:cargo|вантаж\w*|груз)\b")
_RELEASED = re.compile(r"(?iu)\b(?:jettison\w*|dropp?ed|released|скинул\w*|скинула\w*|скинув\w*)\b")
_FALSE_DROP = re.compile(r"(?iu)\bкапсул\w*\b.{0,160}\b(?:скинула|скинув|скинули|скидає)\s+(?:[а-яіїєґ]+\s+){0,3}(?:вантаж\w*|груз)\b")
# Exact indoor collision percentage context. Do not lose the source scope.
_INDOOR_COLLISIONS = re.compile(r"(?iu)\b(?:indoor|у\s+приміщенн\w*|всередин\w*)\b.{0,90}\b(?:collisions?|зіткнен\w*)\b|\b(?:collisions?|зіткнен\w*)\b.{0,90}\b(?:indoor|у\s+приміщенн\w*|всередин\w*)\b")
_COLLISION_OUT = re.compile(r"(?iu)\b(?:зіткнен\w*|колізі\w*)\b")
_INDOOR_OUT = re.compile(r"(?iu)\b(?:приміщенн\w*|всередин\w*|будівл\w*|закрит\w*\s+простор\w*)\b")
_PERCENT = re.compile(r"\b(\d{1,3})\s*%")


def source_action_scope_issues_231(article: Any, final_text: str) -> tuple[str, ...]:
    source = _read(article, "raw_text")[:18000]
    outgoing = str(final_text or "")[:8000]
    if not source or not outgoing:
        return ()
    issues = []
    if (_SPLASHED.search(source) and _CAPSULE.search(source) and _CARGO.search(source)
            and not _RELEASED.search(source) and _FALSE_DROP.search(outgoing)):
        issues.append("FACT_CAPSULE_SPLASHDOWN_NOT_CARGO_DROP_231")
    if _INDOOR_COLLISIONS.search(source) and _COLLISION_OUT.search(outgoing) and not _INDOOR_OUT.search(outgoing):
        source_pct = {m.group(1) for m in _PERCENT.finditer(source)}
        output_pct = {m.group(1) for m in _PERCENT.finditer(outgoing)}
        if source_pct & output_pct:
            issues.append("FACT_INDOOR_COLLISION_SCOPE_LOST_231")
    return tuple(issues)
