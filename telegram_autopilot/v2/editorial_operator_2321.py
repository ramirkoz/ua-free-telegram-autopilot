"""2.3.21 operator topic calibration, without source/fact/Telegram overrides."""
from __future__ import annotations

import re
from typing import Any

_APPOINTMENT = re.compile(
    r"(?iu)\b(?:appoints?|appointed|names?|named|selected|selects|"
    r"признач\w*|обрал\w*|призначен\w*)\b"
)
_AGENCY = re.compile(
    r"(?iu)\b(?:agency|agencies|advertising partner|creative partner|"
    r"lead agency|агенц\w*|агентств\w*)\b"
)
_NOT_YET = re.compile(
    r"(?iu)(?:first work.{0,110}(?:expected|later|upcoming|future)|"
    r"(?:campaign|creative work).{0,100}(?:will launch|to be unveiled|"
    r"expected|planned|coming soon)|"
    r"(?:кампані|проєкт).{0,70}(?:заплан|очікуєт|згодом))"
)
_NOSTALGIA_LISTING = re.compile(
    r"(?iu)(?:ebay|etsy|auction|second.hand|classifieds|"
    r"продаєт|аукціон)"
)


def _text(article: Any, key: str) -> str:
    try:
        return str(article[key] or "")
    except (KeyError, TypeError, IndexError):
        return str(getattr(article, key, "") or "")


def concrete_routine_pr_reason(article: Any, role: str) -> str:
    """Narrow evidence-only veto: appointment is not a finished campaign."""
    if role != "creative":
        return ""
    title = _text(article, "title")
    body = _text(article, "raw_text")
    if _APPOINTMENT.search(title) and _AGENCY.search(title) and _NOT_YET.search(body):
        return "EDITOR_2321_UNREALIZED_AGENCY_APPOINTMENT"
    return ""


def verify_low_confidence_publish(role: str, fit_score: int, article: Any) -> bool:
    """Ask a source-quoted second opinion on internally weak PUBLISH decisions.

    Never apply a blanket low-score rejection: valuable science rows also
    received an unreasonably low raw fit score from the primary model.
    """
    if role not in {"science", "creative"}:
        return False
    if int(fit_score or 0) < 40:
        return True
    title = _text(article, "title")
    return bool(
        role == "creative"
        and (
            (_AGENCY.search(title) and _APPOINTMENT.search(title))
            or _NOSTALGIA_LISTING.search(title)
        )
    )


VERIFY_PUBLISH_PROMPT_2321 = (
    "НЕЗАЛЕЖНИЙ РЕДАКТОР: первинний AI позначив статтю PUBLISH, "
    "але його оцінка суперечлива або є ризик звичайного PR. "
    "Виріши самостійно, чи це конкретна новина для читача цього каналу. "
    "CTRL+UA: дійсно нова наука, технологія або перевірений результат, "
    "а не звичайна побутова інструкція чи відновлення старого приладу. "
    "ПРОДАНО!: готова незвичайна творча ідея, продукт, предметний дизайн "
    "або показана рекламна механіка, не лише призначення агенції, "
    "обіцянка майбутнього запуску чи товар на eBay. "
    "Не вимагай революційності для справді цікавої речі. "
    "Не вигадуй фактів, а при PUBLISH процитуй дослівно від 20 до 180 "
    "символів оригінального SOURCE BODY, які підтверджують цінність. "
    "Без перевірюваної цитати рішення REJECT. "
    'Поверни лише JSON: {"decision":"reject","source_quote":"",'
    '"reason":"конкретне пояснення"}.'
)
