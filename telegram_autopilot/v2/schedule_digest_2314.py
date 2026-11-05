"""2.3.14: concise, source-grounded outage change notices.

Source-only, editorial-scoped guidance/length. Never infer or edit an outage
hour, group or day, and never relax Fact Guard, QA or source-sentence floor.
"""
from __future__ import annotations

import re

from .numeric_schedule_2313 import schedule_guidance

# Require an actual change narrative, not merely a bare table headed "оновлено".
# This signal chooses a *shorter writer target*; editorial inclusion and
# hard two-source-sentence rules are still evaluated independently.
_CHANGE_NARRATIVE = re.compile(
    r"(?iu)(?:\bперенес\w*\b|\bзмінил\w*\b|\bпочина\w*\s+"
    r"(?:на\s+\w+\s+)?пізніш\w*\b|\bтрива\w*\s+"
    r"(?:на\s+\w+\s+)?довш\w*\b|\bна\s+\d+\s*"
    r"(?:хвилин\w*|годин\w*)\s+(?:пізніш\w*|довш\w*)\b)"
)

SOURCE_GROUNDED_DIGEST_RULE_2314 = (
    "ОНОВЛЕННЯ ГРАФІКА: це коротка новина про ЗМІНУ, а не перепис усієї таблиці. "
    "Напиши два або три завершені фактичні речення про прямо підтверджені "
    "черги, старий і новий час та суть зміни. Нічого не домислюй і не "
    "виводь самостійно тривалість або час. Якщо у SOURCE є кілька версій "
    "одного графіка, пріоритет має останнє явно позначене оновлення. "
    "Якщо докладний розклад великий, посилайся на повний графік у "
    "першоджерелі, не копіюй усі рядки. Не добирай обсяг повтореннями, "
    "саморекламою чи загальними фразами; не змішуй старі й нові часи. "
    "Збережи щонайменше два незалежні факти, які явно є у SOURCE.\n"
)


def is_change_digest_2314(raw_source: str) -> bool:
    """Only time-rich, explicitly changed schedules need concise digest limits."""
    value = str(raw_source or "")
    return bool(schedule_guidance(value) and _CHANGE_NARRATIVE.search(value))


def schedule_digest_limits_2314(
    raw_source: str, min_chars: int, max_chars: int,
) -> tuple[int, int]:
    """Target compact reporting without changing any factual acceptance gate."""
    lo, hi = int(min_chars), int(max_chars)
    if not is_change_digest_2314(raw_source):
        return lo, hi
    # Previously a 1036-char source table required 500-750 chars of prose,
    # causing hallucinated padding and looping models despite enough real facts.
    hi = min(hi, 520)
    lo = min(lo, 220, hi)
    return lo, hi


def schedule_digest_instruction_2314(raw_source: str) -> str:
    return SOURCE_GROUNDED_DIGEST_RULE_2314 if is_change_digest_2314(raw_source) else ""
