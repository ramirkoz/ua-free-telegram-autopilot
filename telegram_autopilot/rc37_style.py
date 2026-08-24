from __future__ import annotations

import re
from typing import Any, Mapping

# These are synthetic house-style examples, not copied source material.  They are
# deliberately short: the model should learn the editorial mechanics (hook ->
# useful detail -> stop), not borrow facts or wording into another story.
_STYLE_EXAMPLES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    (
        "science",
        ("space", "galaxy", "astronom", "physics", "moon", "nasa", "telescope", "research", "study"),
        "У центрі Чумацького Шляху знайшли «шрам» від дуже давнього галактичного злиття. "
        "Слід пережив мільярди років і лишився біля ядра, тож астрономи отримали нову точку відліку для історії нашої галактики.\n\n"
        "Ключем стали старі зоряні скупчення: їхній рух і склад дозволили відокремити рештки поглинутої системи від решти Чумацького Шляху.",
    ),
    (
        "windows",
        ("windows", "microsoft", ".net", "software", "driver", "gaming", "pdf"),
        "Серпневе оновлення Windows принесло неприємний бонус: частина програм почала падати під час друку або експорту в PDF.\n\n"
        "Microsoft підтвердила збій у WPF-застосунках. Є тимчасовий обхід, але він послаблює захист, який саме оновлення мало додати.",
    ),
    (
        "cyber",
        ("cisa", "vulnerability", "breach", "malware", "ransomware", "security", "cve", "hack"),
        "Федеральним установам США дали три дні на термінове оновлення Zimbra: уразливість уже використовують у реальних атаках.\n\n"
        "Проблема дозволяє надсилати спеціально сформовані запити й дістатися до виконання команд. Патч уже є, тож головне питання тепер просте: хто встиг оновитися.",
    ),
    (
        "hardware",
        ("chip", "transistor", "semiconductor", "hbm", "gpu", "cpu", "silicon", "sic", "memory"),
        "Транзистор пережив 600°C і продовжив працювати. Для звичайної кремнієвої електроніки це вже територія, де починаються серйозні проблеми.\n\n"
        "Розробники використали процес, сумісний із промисловим виробництвом чипів. Саме це робить результат цікавішим за лабораторний рекорд заради рекорду.",
    ),
    (
        "ai",
        (" ai ", "artificial intelligence", "claude", "chatgpt", "gemini", "model", "agent", "openai", "anthropic"),
        "ШІ-агентам дали більше свободи працювати з браузером і файлами без ручної метушні між інструментами.\n\n"
        "Новий набір API дозволяє агенту виконувати кілька дій поспіль, повторно використовувати завантажені файли й підключати власні навички. Це вже ближче до робочого процесу, а не до чергового чат-вікна.",
    ),
    (
        "weird-tech",
        ("robot", "open source", "github", "tool", "app", "device", "desktop", "utility"),
        "На робочий стіл поселили цифрову муху з поведінкою, побудованою на реальній схемі нервових зв’язків дрозофіли. Вона гуляє по вікнах, реагує на курсор і навіть «засинає».\n\n"
        "Найцікавіше тут не анімація: частина реакцій виникає після активації конкретних нейронів, а не прописана окремими сценаріями.",
    ),
)

_STOP = {
    "the", "and", "for", "with", "from", "that", "this", "what", "how", "why",
    "про", "для", "або", "який", "яка", "яке", "після", "через", "новий", "нова", "нове",
}


def _text(article: Mapping[str, Any] | Any) -> str:
    def value(key: str) -> str:
        try:
            return str(article[key] or "")
        except Exception:
            return ""
    return f" {value('title')} {value('raw_text')[:5000]} ".casefold()


def style_examples_for_article(article: Mapping[str, Any] | Any, *, limit: int = 2) -> tuple[str, ...]:
    haystack = _text(article)
    scored: list[tuple[int, int, str]] = []
    for index, (_name, keywords, example) in enumerate(_STYLE_EXAMPLES):
        score = sum(2 if f" {token.strip()} " in haystack else 1 for token in keywords if token in haystack)
        scored.append((score, -index, example))
    ranked = [example for score, _order, example in sorted(scored, reverse=True) if score > 0]
    if not ranked:
        ranked = [_STYLE_EXAMPLES[0][2], _STYLE_EXAMPLES[5][2]]
    return tuple(ranked[: max(1, int(limit))])


def style_prompt_examples(article: Mapping[str, Any] | Any, *, limit: int = 2) -> str:
    examples = style_examples_for_article(article, limit=limit)
    blocks = []
    for i, text in enumerate(examples, 1):
        blocks.append(f"STYLE EXAMPLE {i} (UNRELATED FACTS — NEVER COPY THEM INTO THE CURRENT STORY):\n{text}")
    return "\n\n".join(blocks)


_GENERIC_OPENERS = (
    "компанія ",
    "дослідники ",
    "вчені ",
    "у новому дослідженні ",
    "за даними ",
    "microsoft підтвердила",
    "google повідомила",
    "apple повідомила",
    "anthropic повідомила",
    "openai повідомила",
)

_FORMULAIC = (
    "для широкої аудиторії",
    "це важливо, тому що",
    "це важливо як",
    "варто зазначити",
    "окремо варто зазначити",
    "таким чином",
    "це демонструє",
    "це підкреслює",
    "для користувачів це означає",
)


def interest_style_issues(text: str) -> tuple[str, ...]:
    value = str(text or "").strip()
    if not value:
        return ("порожній текст",)
    low = value.casefold()
    issues: list[str] = []
    first = re.split(r"(?<=[.!?…])\s+", value, maxsplit=1)[0].strip().casefold()
    if any(first.startswith(prefix) for prefix in _GENERIC_OPENERS):
        issues.append("слабкий канцелярський початок замість новинного гачка")
    hits = [phrase for phrase in _FORMULAIC if phrase in low]
    if hits:
        issues.append("шаблонні AI-переходи/мета-пояснення")
    paragraphs = [p.strip() for p in re.split(r"\n+", value) if p.strip()]
    if len(paragraphs) == 4:
        lengths = [len(p) for p in paragraphs]
        avg = sum(lengths) / 4
        if avg and max(abs(length - avg) for length in lengths) / avg < 0.32:
            issues.append("надто симетрична чотириабзацна AI-структура")
    transitions = sum(low.count(word) for word in ("водночас", "окремо", "також", "при цьому"))
    if transitions >= 4:
        issues.append("забагато службових переходів")
    sentences = [s.strip() for s in re.split(r"(?<=[.!?…])\s+", " ".join(paragraphs)) if s.strip()]
    if len(sentences) >= 6:
        starters = [re.sub(r"[^а-яіїєґa-z0-9]+", "", s.split()[0].casefold()) for s in sentences if s.split()]
        if starters and max(starters.count(x) for x in set(starters)) >= 3:
            issues.append("монотонні однакові початки речень")
    if len(value) >= 760 and len(sentences) >= 7 and not any(mark in value for mark in ("—", ":", "?", "!", "«")):
        issues.append("занадто рівний безособовий ритм")
    return tuple(dict.fromkeys(issues))


def preserves_story_reedit(original: str, polished: str) -> bool:
    """Allow a real rewrite, not just grammar polish, while forbidding expansion.

    RC36 required 64% of the final vocabulary to be present in the previous draft.
    That was safe but rejected many legitimate hook-first edits. RC37 keeps the
    strong invariants (no new numbers, no new Latin/named anchors, bounded length)
    and relaxes lexical overlap because the article-level Fact Guard runs again.
    """
    from .grammar_guard import _anchors, _content_tokens, _norm_numbers

    a = str(original or "").strip()
    b = str(polished or "").strip()
    if not a or not b:
        return False
    ratio = len(b) / max(1, len(a))
    if ratio < 0.40 or ratio > 1.12:
        return False
    if not _norm_numbers(b).issubset(_norm_numbers(a)):
        return False
    if not _anchors(b).issubset(_anchors(a)):
        return False
    a_tokens = _content_tokens(a)
    b_tokens = _content_tokens(b)
    if not b_tokens:
        return False
    if not a_tokens:
        return True
    return len(a_tokens & b_tokens) / len(b_tokens) >= 0.50
