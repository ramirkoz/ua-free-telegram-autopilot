"""v2.2.51 conservative DRAFT -> FINAL factual-regression checks.

Not general translation entailment. Only report provable regressions between
two Ukrainian versions of the SAME source. Never repair facts automatically.
Any blocked candidate is returned to the existing trusted editor validator.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_SENTENCE = re.compile(r"(?<=[.!?…])\s+|\n+")
_WORD = re.compile(r"(?iu)\b[а-яіїєґa-z]{4,}\b")
_MODAL = re.compile(
    r"(?iu)\b(?:може|можуть|могли|могла|могло|міг|могла\s+б|могли\s+б|"
    r"ймовірн\w*|імовірн\w*|можлив\w*|припуска\w*|"
    r"гіпотез\w*|попередн\w*|нібито|за\s+оцінк\w*|за\s+припущенн\w*)\b"
)
_STOP = frozenset({
    "дослі", "науко", "зазна", "повід", "припу", "можли", "могли",
    "імові", "ймові", "попер", "вважа", "ствер", "назив", "автор",
    "цього", "також", "своїх", "після", "через", "якого", "яких",
    "якому", "зокре", "підтр", "іншог", "стало", "виявл", "самого",
    "друге", "третє",
})
_ROLE_SOURCE = re.compile(
    r"(?iu)\b(?:працюва\w*\s+над|брав\s+участь\s+у\s+створенн\w*|"
    r"брала\s+участь\s+у\s+створенн\w*)\b"
)
_ROLE_UPGRADE = re.compile(
    r"(?iu)\b(?:автор(?:ом|ка|кою)?|творц(?:ем|ею)|"
    r"створив|створила)\s+(?:[«“\"]|мультфільм\w*\s+[«“\"])"
)
_QUOTED = re.compile(r"[«“\"]([^»”\"]{3,90})[»”\"]")
_REVIEW_PROMPT = """SOURCE → DRAFT → FINAL, ЖОРСТКИЙ СЕМАНТИЧНИЙ КОНТРОЛЬ:
- Зістав кожне фінальне твердження з першоджерелом, а не з красивим ANGLE.
- Не перетворюй «могли», «ймовірно», «припускають», «may/might/could» на встановлений факт.
- «Працював над фільмом» не означає «автор фільму». Перевір роль кожної особи.
- Не уточнюй «внутрішнє/зовнішнє», «перше/друге» чи «причина/наслідок» без SOURCE.
- Не додавай оцінку журналіста як офіційну позицію бренду чи установи.
- Мовна редактура НЕ дає дозволу змінювати факти. Якщо немає підтримки SOURCE, прибери фразу.
""".strip()


@dataclass(frozen=True, slots=True)
class DeltaIssue:
    code: str
    evidence: str


def _sentences(value: str) -> tuple[str, ...]:
    return tuple(
        part.strip(" \t•-")
        for part in _SENTENCE.split(str(value or ""))
        if part.strip(" \t•-")
    )


def _stems(value: str) -> set[str]:
    # Conservative root similarity for Ukrainian endings; no semantic claims.
    return {
        word[:5].casefold() for word in _WORD.findall(value)
        if len(word) >= 5 and word[:5].casefold() not in _STOP
    }


def _aligned(old: str, new: str) -> bool:
    a, b = _stems(old), _stems(new)
    if not a or not b:
        return False
    shared = len(a & b)
    return shared >= 3 and shared / max(1, min(len(a), len(b))) >= 0.7


def draft_final_regressions(draft: str, final: str) -> tuple[DeltaIssue, ...]:
    """Detect high-confidence certainty and credit escalations.

    A valid shortened final may omit a qualified statement entirely. It is
    blocked only if a substantively ALIGNED statement survives unqualified.
    This helper deliberately makes no claims about English-to-Ukrainian NLI.
    """
    original = str(draft or "").strip()
    revised = str(final or "").strip()
    if not original or not revised or original == revised:
        return ()
    issues: list[DeltaIssue] = []
    old_statements = _sentences(original)
    new_statements = _sentences(revised)
    for old in old_statements:
        if not _MODAL.search(old):
            continue
        for new in new_statements:
            if _MODAL.search(new) or not _aligned(old, new):
                continue
            issues.append(DeltaIssue(
                "EDITORIAL_CERTAINTY_ESCALATION_251",
                "В умовному DRAFT зникла модальність у FINAL: " + old[:120],
            ))
            break
    if _ROLE_SOURCE.search(original) and _ROLE_UPGRADE.search(revised):
        source_quotes = [_stems(q) for q in _QUOTED.findall(original)]
        final_quotes = [_stems(q) for q in _QUOTED.findall(revised)]
        # Require at least one specifically shared work, not just same person.
        if any(len(left & right) >= 1 for left in source_quotes for right in final_quotes):
            issues.append(DeltaIssue(
                "EDITORIAL_ROLE_PROMOTION_251",
                "У DRAFT людина працювала над твором, а FINAL називає її автором.",
            ))
    return tuple(dict.fromkeys(issues))


FINAL_CLAIM_REVIEW_RULE = _REVIEW_PROMPT
