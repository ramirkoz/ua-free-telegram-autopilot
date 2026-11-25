"""Owner-approved full-story editorial contract. No additional model calls."""
from __future__ import annotations
import re


def editorial_length_targets(source_chars: int, configured_min: int,
                             configured_max: int, hard: int) -> tuple[int, int, int]:
    if source_chars < 650:
        return configured_min, configured_max, hard
    # Use the actual body budget, not an old 300-character configuration.
    target = 740 if source_chars >= 1200 else 600
    ceiling = min(hard, max(configured_max, 850))
    return min(ceiling, max(configured_min, min(target, ceiling - 30))), ceiling, hard


def full_story_instruction_2357(channel, article, hard: int) -> str:
    if str(getattr(getattr(channel, "mode", None), "value", getattr(channel, "mode", ""))).lower() != "editorial":
        return ""
    return (f"ПОВНА НОВИНА 2.3.57. За змістовного SOURCE використовуй приблизно 700–850 "
            f"символів, але не більше {hard} символів тіла; не пиши короткий підпис "
            "замість новини. Почни з головної події, поясни простими словами що сталося, "
            "як це працює, наведи конкретний приклад або результат із SOURCE. "
            "Збережи обмеження, невизначеність, статус патенту/дослідження та важливі факти. "
            "Фінальний редактор не викидає змістовні абзаци або пояснення: виправляє мову, "
            "а не стискає повну новину. Не додавай води або непідтверджених фактів. "
            "Короткий текст допустимий лише коли джерело справді коротке або бракує фактів. "
            "Пиши природно, 2–4 короткими абзацами, без канцеляриту.")


_CAVEAT = re.compile(r"не\s+(?:довод\w*|означ\w*|гарант\w*|підтвердж\w*)|"
                     r"(?:поки|ще)\s+не\s+|не\s+відомо|невідомо|"
                     r"(?:лише|тільки)\s+(?:патент\w*|гіпотез\w*|припущенн\w*)", re.I)


def final_story_loss_2357(draft: str, final: str, hard: int) -> str:
    # A genuine factual correction may be shorter; it must not silently replace
    # a complete draft with a fragment. Existing full QA decides draft fallback.
    before, after = len(draft.strip()), len(final.strip())
    if before >= 500 and after < min(int(before * 0.76), max(80, hard - 60)):
        return "FINAL_STORY_LOSS_2357: істотне скорочення змістовної чернетки"
    if _CAVEAT.search(draft) and not _CAVEAT.search(final) and after < before:
        return "FINAL_STORY_LOSS_2357: втрачено застереження або невизначеність"
    return ""
