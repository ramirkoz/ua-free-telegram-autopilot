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
    """Reject minute-lived monitoring alerts only when channel policy opts in."""
    if channel.mode != ChannelMode.MONITORING:
        return ""
    rules = str(channel.policy.rejection_rules or "")
    if _POLICY_MARKER not in rules:
        return ""

    low = (_value(article, "title") + "\n" + _value(article, "raw_text")).casefold()
    durable_aftermath = any(
        token in low
        for token in (
            "було атаковано", "була атакована", "був атакований", "після атаки",
            "внаслідок атаки", "наслідки атаки", "пошкоджено", "зруйновано",
            "ліквідували наслідки", "відновили після",
        )
    )
    if durable_aftermath:
        return ""

    patterns = (
        r"\bповітрян\w*\s+тривог",
        r"\bвідбій\b.*\bтривог",
        r"\bтривог\w*\s+скас",
        r"\bзагроз\w*\b.{0,80}\b(бпла|дрон\w*|ракета|шахед\w*|авіац\w*)",
        r"\b(бпла|дрон\w*|ракета|шахед\w*|авіац\w*)\b.{0,80}\bзагроз\w*",
        r"\b(бпла|дрон\w*|ракета|шахед\w*|мопед\w*|повітрян\w*\s+ціл\w*)\b.{0,120}\b(летить|летів|пролетів|пролітає|рухаєть\w*|рух\w*|курс\w*|напрям\w*)",
        r"\b(летить|летів|пролетів|пролітає|рухаєть\w*|рух\w*|курс\w*|напрям\w*)\b.{0,120}\b(бпла|дрон\w*|ракета|шахед\w*|мопед\w*|повітрян\w*\s+ціл\w*)",
        r"\b(зафіксували|побачили|чути|видно)\b.{0,120}\b(летить|пролетів|рух\w*|мопед\w*|бпла|дрон\w*|ракета|шахед\w*)",
        r"\b(зараз|наразі|прямо\s+зараз|цієї\s+миті)\b.{0,100}\b(палає|горить|пожеж\w*|вибух\w*|дим\w*|летить|рухаєть\w*|загроз\w*)",
        r"\b(щойно|тільки\s+що)\b.{0,100}\b(пролетів|побачили|зафіксували|вибух\w*|загоріл\w*|палає|горить)",
    )
    if any(re.search(pattern, low, re.I) for pattern in patterns):
        return "Оперативна live-now подія, що втрачає актуальність у 15-хвилинному циклі моніторингу"
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
