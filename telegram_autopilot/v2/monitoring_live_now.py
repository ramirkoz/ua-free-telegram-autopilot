from __future__ import annotations

import re
from typing import Any, Mapping

from .domain import ChannelConfig, ChannelMode, Decision

_POLICY_MARKER = "[LIVE_NOW_RC96]"


def _value(row: Mapping[str, Any] | Any, key: str) -> str:
    try:
        value = row[key]
    except Exception:
        value = getattr(row, key, "")
    return str(value or "")


def live_now_exclusion(channel: ChannelConfig, article: Any) -> str:
    """Reject minute-lived or still-unsettled monitoring events when policy opts in.

    A 15-minute monitoring cycle is not a real-time alert service. The gate rejects
    explicit alerts/movement and first operational reports whose facts are still
    changing. Stable aftermath remains eligible only when the report contains a
    concrete settled result rather than merely saying that an impact occurred.
    """
    if channel.mode != ChannelMode.MONITORING:
        return ""
    rules = str(channel.policy.rejection_rules or "")
    if _POLICY_MARKER not in rules:
        return ""

    low = (_value(article, "title") + "\n" + _value(article, "raw_text")).casefold()

    # RC99: do not let AI invent a news item from a bare warning such as
    # "Новомиколаївка, уважно". A monitoring item must contain an actual event,
    # action, consequence or scheduled change before it reaches generative AI.
    compact = re.sub(r"\s+", " ", low).strip()
    warning_only = any(token in compact for token in ("уважно", "увага", "важливо", "терміново", "обережно"))
    concrete_context = any(token in compact for token in (
        "пошкод", "зруйн", "поран", "загин", "постраждал", "пожеж", "відключ", "ремонт",
        "віднов", "відкрит", "закрит", "перекрит", "зміни", "авар", "влучан", "обстріл",
        "тривог", "евакуац", "вода", "електро", "газ", "опален", "транспорт", "дорог", "школ",
        "лікар", "допомог", "виплат", "графік", "розклад", "рішення", "засідан", "ярмар", "поді",
    ))
    if warning_only and len(compact) <= 180 and not concrete_context:
        return "Недостатньо контексту: джерело містить лише попередження без події, факту або дії"

    settled_aftermath = any(
        token in low
        for token in (
            "внаслідок нічної атаки", "внаслідок ранкової атаки", "за підсумками атаки",
            "підсумки атаки", "підтвердили наслідки", "внаслідок обстрілу пошкоджено",
            "пошкоджено ", "зруйновано ", "госпіталізовано ", "загинул", "поранен",
            "ліквідацію пожежі завершено", "пожежу ліквідовано", "ліквідували пожеж",
            "завершили ліквідацію", "відновили після", "наслідки атаки за ніч",
        )
    )
    strong_settled_result = bool(
        re.search(r"\b(?:пошкоджено|зруйновано)\b[^.!?]{0,100}\b\d+\b", low, re.I)
        or re.search(r"\b\d+\b[^.!?]{0,80}\b(?:поранен|постраждал|загинул|будин|квартир|авто)\w*", low, re.I)
        or any(token in low for token in (
            "ліквідацію пожежі завершено", "пожежу ліквідовано", "ліквідували пожеж",
            "завершили ліквідацію", "офіційно підтвердили наслідки", "за підсумками атаки",
        ))
    )

    hard_unfolding_patterns = (
        r"\b(зараз|наразі|прямо\s+зараз|цієї\s+миті|у\s+ці\s+хвилини)\b.{0,140}\b(палає|горить|пожеж\w*|вибух\w*|дим\w*|задимлен\w*|летить|рухаєть\w*|загроз\w*)",
        r"\b(щойно|тільки\s+що|кілька\s+хвилин\s+тому)\b.{0,160}\b(пролетів|побачили|зафіксували|вибух\w*|загоріл\w*|палає|горить|атак\w*|удар\w*)",
        r"\b(пролунал\w*|чутно|чути)\b.{0,100}\bвибух\w*",
        r"\b(видно|помітили)\b.{0,100}\b(дим|задимлен\w*|пожеж\w*|полум.?я)",
        r"\bпопередньо\b.{0,180}\b(удар|влучан|постраждал|загибл|пошкоджен|атак|обійшл)\w*",
    )
    if any(re.search(pattern, low, re.I) for pattern in hard_unfolding_patterns):
        return "Подія ще відбувається або є первинним оперативним повідомленням; для 15-хвилинного моніторингу вона неактуальна"

    soft_unfolding_patterns = (
        r"\b(удар\w*\s+прийш|влучан\w*)\b.{0,180}\b(поблизу|район|об.?єкт|будин|міст|дим|пожеж)",
        r"\b(служб\w*|рятувальник\w*)\b.{0,100}\b(працюють|працює|виїхали|прямують|на\s+місці)\b",
    )
    if not strong_settled_result and any(re.search(pattern, low, re.I) for pattern in soft_unfolding_patterns):
        return "Первинне оперативне повідомлення без стабілізованих підсумків"

    # RC98: phrases such as "зафіксовано влучання" were slipping through when a
    # first report also contained a generic word like "пошкоджено".  A first impact
    # notice is not a settled aftermath summary unless it contains a concrete final
    # result (counts/confirmed consequences/completed response).
    first_impact_report = any(
        re.search(pattern, low, re.I)
        for pattern in (
            r"\b(?:зафіксован[оі]|зафіксували)\b.{0,100}\bвлучан\w*",
            r"\b(?:сталося|було|є)\s+влучан\w*",
            r"\b(?:під\s+ранок|сьогодні\s+вранці|цієї\s+ночі)\b.{0,140}\b(?:влучан\w*|приліт\w*|удар\w*)",
            r"\b(?:приліт\w*|влучан\w*)\b.{0,100}\b(?:по|у|в)\s+(?:район|об.?єкт|будин|міст)",
        )
    )
    if first_impact_report and not strong_settled_result:
        return "Первинне повідомлення про влучання/удар без стабілізованих підсумків"

    patterns = (
        r"\bповітрян\w*\s+тривог",
        r"\bвідбій\b.*\bтривог",
        r"\bтривог\w*\s+скас",
        r"\bзагроз\w*\b.{0,80}\b(бпла|дрон\w*|ракета|шахед\w*|авіац\w*)",
        r"\b(бпла|дрон\w*|ракета|шахед\w*|авіац\w*)\b.{0,80}\bзагроз\w*",
        r"\b(бпла|дрон\w*|ракета|шахед\w*|мопед\w*|повітрян\w*\s+ціл\w*)\b.{0,120}\b(летить|летів|пролетів|пролітає|рухаєть\w*|рух\w*|курс\w*|напрям\w*)",
        r"\b(летить|летів|пролетів|пролітає|рухаєть\w*|рух\w*|курс\w*|напрям\w*)\b.{0,120}\b(бпла|дрон\w*|ракета|шахед\w*|мопед\w*|повітрян\w*\s+ціл\w*)",
        r"\b(зафіксували|побачили|чути|видно)\b.{0,120}\b(летить|пролетів|рух\w*|мопед\w*|бпла|дрон\w*|ракета|шахед\w*)",
    )
    if any(re.search(pattern, low, re.I) for pattern in patterns):
        return "Оперативна live-now подія, що втрачає актуальність у 15-хвилинному циклі моніторингу"

    war_context = any(token in low for token in ("росій", "ворож", "бпла", "дрон", "шахед", "ракет", "обстріл", "удар", "запоріж"))
    attack_now = war_context and any(token in low for token in ("атакували", "атаковано", "обстріляли", "завдали удар", "вибух"))
    if attack_now and not settled_aftermath and not strong_settled_result:
        return "Первинне повідомлення про атаку/вибух без стабілізованих підсумків"

    return ""


def install_monitoring_live_now_gate() -> None:
    """Put the deterministic channel-policy gate before the AI monitoring selector."""
    from .editorial import EditorialEngine, EditorialOutcome

    if getattr(EditorialEngine, "_live_now_rc96_installed", False):
        return
    previous = EditorialEngine._select_monitoring

    def wrapped(self, channel: ChannelConfig, article: Any):
        reason = live_now_exclusion(channel, article)
        if reason:
            return EditorialOutcome(Decision.REJECT, reason="MONITORING_LIVE_NOW_REJECT: " + reason, fit_score=0)
        return previous(self, channel, article)

    EditorialEngine._select_monitoring = wrapped
    EditorialEngine._live_now_rc96_installed = True
