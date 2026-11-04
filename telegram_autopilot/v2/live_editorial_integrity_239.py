"""2.3.9: conservative, evidence-first local monitoring and output guards.

Publisher URLs and social channel brands are never geographic evidence.
These checks do not alter operator Data, delivery receipts or interval limits.
"""
from __future__ import annotations
import re
from typing import Any


def _field(row: Any, key: str) -> str:
    try:
        return str(row[key] or "")
    except (TypeError, KeyError, IndexError):
        return str(getattr(row, key, "") or "")


_URL = re.compile(r"https?://\S+", re.I)
_LOCAL = re.compile(
    r"(?iu)запоріжж|запорізьк|енергодар|гуляйпол|мелітопол|бердянськ|"
    r"оріхів|полог[иів]|токмак|василівк|комишувах|великобілозер|"
    r"дніпрорудн|кушугум|вільнян|приморськ|чернігівськ\w*\s+громад"
)
_OTHER_CITY = re.compile(
    r"(?iu)\b(?:києв[а-яіїєґ]*|київ[а-яіїєґ]*|львов[а-яіїєґ]*|"
    r"львів[а-яіїєґ]*|одес[а-яіїєґ]*|харків[а-яіїєґ]*|"
    r"полтав[а-яіїєґ]*|чернівц[а-яіїєґ]*|ужгород[а-яіїєґ]*|"
    r"луцьк[а-яіїєґ]*|рівн[а-яіїєґ]*)\b"
)
_POLITICAL_REACTION = re.compile(
    r"(?iu)fox\s*news|аха{3,}|кепарик|рудий|демократичн\w*\s+парті\w*|трамп\w*"
)
_NATIONAL_FINANCE = re.compile(
    r"(?iu)(?:курс\s+(?:долара|євро)|національн\w*\s+банк\w*|"
    r"нбу\s+(?:оприлюднив|встановив)\s+курс)"
)
_SPECIAL_LOCAL = re.compile(r"(?iu)(?:впо|переселенц|громад|мешканц|жител|вихідц|евакуйован)")
_CLAIMED_STATS = re.compile(
    r"(?iu)(?:населенн[яі]|мешканц[іві])[^.!?\n]{0,90}"
    r"(?:третин[ауи]|\d+\s*(?:тис|тисяч|мільйон))"
)
_UNATTRIBUTED = re.compile(r"(?iu)\b(?:це\s+статистика|ніхто\s+не\s+каже)\b")
_UA = re.compile(r"[А-Яа-яІіЇїЄєҐґ]")
_ARABIC_HEBREW = re.compile(r"[\u0600-\u06ff\u0590-\u05ff]")
_MISSING_LINK_CUE = re.compile(
    r"(?iu)(?:детал[іьи]\s+(?:вакансій|вакансії)[^.!?\n]{0,35}"
    r"(?:за\s+посиланням|у\s+посиланні)|"
    r"(?:переглянути|дізнатися)[^.!?\n]{0,50}за\s+посиланням)"
)
_LEGAL_CASE = re.compile(
    r"(?iu)\b(?:обвинувальн\w*\s+акт|передано\s+до\s+суду|"
    r"скеровано\s+до\s+суду|обвинувачен\w*)\b"
)
_LEGAL_CERTAINTY = re.compile(
    r"(?iu)\b(?:доведено\s+що|винні\s+у|"
    r"злочинц[іів]+|шахраї\s+привласнили)\b"
)


def monitoring_scope_issue(article: Any) -> str:
    """Reject narrow, verified out-of-scope patterns; do not ban national civic services."""
    raw = _URL.sub(" ", _field(article, "raw_text"))
    raw = re.split(r"(?iu)\bми\s+в\s*[📱📲]", raw, maxsplit=1)[0]
    title = _URL.sub(" ", _field(article, "title"))
    body = (title + "\n" + raw).strip()
    if _LOCAL.search(body):
        population = _CLAIMED_STATS.search(body) or (
            "третин" in body.casefold() and "населен" in body.casefold()
        )
        if population and _UNATTRIBUTED.search(body) and not re.search(
            r"(?iu)\b(?:держстат|офіційн\w*\s+статистик|даними\s+\w+|"
            r"дослідженн|опитуванн|звіту\s+\w+)\b", body
        ):
            return "MONITORING_UNSUPPORTED_POPULATION_STATS_239"
        return ""
    if _POLITICAL_REACTION.search(body) and not re.search(
        r"(?iu)\b(?:місцев\w*\s+обран|впо|громад|україн\w*\s+міністерств)\b", body
    ):
        return "MONITORING_EXTERNAL_POLITICAL_REACTION_239"
    if _NATIONAL_FINANCE.search(body):
        return "MONITORING_NATIONAL_FINANCE_NO_LOCAL_EVENT_239"
    if _OTHER_CITY.search(body) and not _SPECIAL_LOCAL.search(body):
        return "MONITORING_OTHER_REGION_ONLY_239"
    return ""


def final_integrity_issues(article: Any, text: str) -> tuple[str, ...]:
    """Hard-stop mixed-script typos, broken actionable pointers, and claims of guilt."""
    value = str(text or "")
    raw = _field(article, "raw_text")
    issues: list[str] = []
    for word in re.findall(r"[^\s.,:;!?()\[\]{}«»]+", value):
        if _UA.search(word) and _ARABIC_HEBREW.search(word):
            issues.append("MIXED_SCRIPT_WORD_239")
            break
    if _MISSING_LINK_CUE.search(value) and not re.search(r"https?://", value, re.I):
        issues.append("ACTION_LINK_PLACEHOLDER_239")
    if _LEGAL_CASE.search(raw) and _LEGAL_CERTAINTY.search(value):
        issues.append("UNPRESUMED_LEGAL_GUILT_239")
    return tuple(issues)
