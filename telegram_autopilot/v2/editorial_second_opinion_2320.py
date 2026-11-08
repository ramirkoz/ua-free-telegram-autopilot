"""2.3.20: bounded source-verifiable second opinion for operator false negatives.

Only called AFTER standard source, hard-policy and editorial checks; never
accepts a prior duplicate, stale, promo, missing-source, or missing-media case.
The independent model cannot override downstream Fact/Media/Telegram safety.
"""
from __future__ import annotations

import re
from typing import Any, Mapping

_HARD_CODES = frozenset({
    "duplicate", "stale", "insufficient_facts", "unsafe", "source_missing",
    "unverified", "price_promo", "media_required",
})
_PROMO = re.compile(
    r"(?iu)\b(?:coupon\w*|discount\w*|cashback|clearance|"
    r"знижк\w*|розпродаж\w*|промокод\w*|купони?)\b"
)
_CREATIVE = re.compile(
    r"(?iu)(?:design|designed|art(?:ist|work)?|creative|"
    r"campaign|ad(?:vertis(?:ing|ement))?|brand|"
    r"prototype|invention|gadget|device|concept|"
    r"home|house|ring|oled|e.?ink|visual|"
    r"illustration|sculpture|gaming|game|"
    r"furniture|packaging|logo|object|"
    r"дизайн|креатив|реклам|кампані|прототип|"
    r"пристр|винахід|будин|перст|ілюзі|упаков|"
    r"мистецтв|гаджет|предмет)"
)
_SCIENCE = re.compile(
    r"(?iu)(?:research|scientist|science|NASA|"
    r"space|moon|Artemis|ai |artificial intelligence|"
    r"robot|study|medical|brain|tech|cyber|"
    r"security|sensor|microchip|energy|router|"
    r"космос|наук|дослідж|вчен|медицин|"
    r"робот|технолог|кібер|сенсор|штучн)"
)


def _field(article: Any, key: str) -> str:
    try:
        return str(article[key] or "")
    except (KeyError, TypeError, IndexError):
        return str(getattr(article, key, "") or "")


def eligible_second_opinion_2320(
    article: Any, role: str, reject_code: str = "",
) -> bool:
    """Signal only, not publication authorization; no historic-ID overrides."""
    if role not in {"creative", "science"}:
        return False
    if str(reject_code or "").casefold().strip() in _HARD_CODES:
        return False
    title = _field(article, "title").strip()
    body = _field(article, "raw_text").strip()
    if len(title) < 14 or len(body) < 220:
        return False
    if len(re.findall(r"[.!?](?:\s|$)", body)) < 2:
        return False
    if _PROMO.search(title):
        return False
    return bool((_CREATIVE if role == "creative" else _SCIENCE).search(title))


def verified_second_opinion_2320(value: Mapping[str, Any], article: Any) -> bool:
    """A second model's positive decision MUST cite real source body text."""
    if str(value.get("decision") or "").casefold().strip() != "publish":
        return False
    quote = " ".join(str(value.get("source_quote") or "").casefold().split())
    source = " ".join(_field(article, "raw_text").casefold().split())
    return 20 <= len(quote) <= 180 and quote in source


SECOND_OPINION_INSTRUCTION_2320 = """
НЕЗАЛЕЖНА РЕДАКТОРСЬКА ПЕРЕВІРКА ПІСЛЯ ПЕРШОЇ ВІДМОВИ.
Редактор вручну підтвердив чимало цікавих наукових і креативних тем,
які первинний селектор відкинув як недостатньо сенсаційні або «вузькі».
Самостійно виріши: чи є в SOURCE конкретна новина, оригінальна форма,
креативна механіка, незвична функція або перевірений науковий результат?
Для ПРОДАНО! не вимагай вірусності, ROI чи рекламного бюджету.
Відхиляй звичайний PR, добірки покупок, слабкі каталогові описи,
спекуляції й бездоказові твердження. Не вигадуй цікавинку.
Якщо обираєш publish, процитуй ДОСЛІВНО 20–180 символів
із SOURCE BODY, які доводять позитивне рішення. Без точної цитати REJECT.
Це лише тематична оцінка. Fact Guard, медіа й дедуплікація незалежні.
Поверни виключно JSON:
{"decision":"reject","source_quote":"","reason":"коротка конкретна причина"}
""".strip()
