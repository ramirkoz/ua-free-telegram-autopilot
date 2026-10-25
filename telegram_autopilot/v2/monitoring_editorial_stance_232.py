"""2.2.32: prevent question/opinion laundering in monitoring Telegram copy.

The original publisher may report a verifiable statistic and then speculate,
mock or ask a rhetorical question. A rewrite is not allowed to present that
question as a confirmed event or causal explanation. This is intentionally
narrow: it never marks a normal local event false solely for containing '?'.
"""
from __future__ import annotations

import re
from typing import Any

_SPLIT = re.compile(r"(?<=[.!?…])\s+|\n+")
_WORD = re.compile(r"(?iu)[а-яіїєґa-z0-9]{5,}")
_STOP = frozenset({
    "цього", "цьому", "також", "після", "через", "тобто", "тільки",
    "можливо", "ймовірно", "будуть", "будемо", "всього", "зараз",
    "цього", "коли", "чому", "який", "яких", "якою", "більш",
    "дуже", "стало", "стали", "понад", "робота", "роботи",
    "сказали", "повідомили", "запитали", "нібито",
})
_SOURCE_SARCASM = re.compile(
    r"(?iu)(?:\bоце\s+так\b|\bд[уУ]{3,}же\b|"
    r"\bдуже\s+важлив[а-яіїєґ]*\s+[«\"']|🤷|🤦)"
)
_OUTPUT_EDITORIAL_VOICE = re.compile(
    r"(?iu)\bоце\s+так\b|\bд[уУ]{3,}же\b|"
    r"\b(?:ну\s+і|дивовижн[а-яіїєґ]*\s+робот[а-яіїєґ]*)\b"
)
_MONEY_CLAIM = re.compile(
    r"(?iu)\b(\d{1,4}(?:[,.]\d{1,2})?)\s*"
    r"(?:млн|мільйон[а-яіїєґ]*|тис[а-яіїєґ]*)\s*"
    r"(?:грн|грив[а-яіїєґ]*)\b"
)
# Explicit *reporting of the publisher's question or commentary* is different
# from the bot independently asserting its premise.
_ATTRIBUTION = re.compile(
    r"(?iu)\b(?:"
    r"редакці[яї]\s+(?:запитує|іронізує|припускає|вважає|пише|стверджує)"
    r"|автор[и]?\s+(?:запитує|іронізує|припускає|вважає)"
    r"|видання\s+(?:запитує|іронізує|припускає|вважає)"
    r"|на\s+думку\s+(?:автора|редакції)"
    r"|риторичн[а-яіїєґ]*\s+питанн[а-яіїєґ]*"
    r"|за\s+(?:припущенням|версією)\s+редакції"
    r"|нібито|ймовірно|можливо)\b"
)


def _value(article: Any, field: str) -> str:
    try:
        result = article[field]
    except (KeyError, IndexError, TypeError):
        result = getattr(article, field, "")
    return str(result or "")


def _stems(text: str) -> set[str]:
    return {
        w[:5] for w in (m.group(0).casefold() for m in _WORD.finditer(text))
        if w not in _STOP
    }


def _aligned(a: set[str], b: set[str], *, threshold: float = .65) -> bool:
    shared = len(a & b)
    return shared >= 3 and shared / max(1, min(len(a), len(b))) >= threshold


def _parts(text: str) -> list[str]:
    return [s.strip() for s in _SPLIT.split(text) if s.strip()]


def monitoring_editorial_question_reason(article: Any, final_text: str) -> str:
    """Return a high-confidence reason when a source question becomes a fact.

    Inspect immutable raw source and output only, not generated title or angle.
    If an independent declarative source statement corroborates the final
    sentence, allow it. Source questions that remain questions or are clearly
    attributed to the publisher remain eligible.
    """
    raw = _value(article, "raw_text")[:12000]
    output = str(final_text or "")
    if not raw or not output or "?" not in raw:
        return ""
    original = _parts(raw)
    questions = [s for s in original if s.rstrip().endswith("?") and len(_stems(s)) >= 3]
    if not questions:
        return ""
    declaratives = [s for s in original if "?" not in s and len(_stems(s)) >= 3]
    for out in _parts(output):
        if "?" in out or _ATTRIBUTION.search(out):
            continue
        out_terms = _stems(out)
        if len(out_terms) < 3:
            continue
        for q in questions:
            q_terms = _stems(q)
            if not _aligned(q_terms, out_terms):
                continue
            # A repeated claim from an independently affirmative source
            # sentence is not an invention just because a question also occurs.
            if any(_aligned(_stems(d), out_terms, threshold=.75) for d in declaratives):
                continue
            return "MONITORING_EDITORIAL_QUESTION_AS_FACT"
    return ""


def monitoring_unattributed_sarcasm_reason(article: Any, final_text: str) -> str:
    """Catch blatant re-use of a source newsroom's ironic narrator voice."""
    source = _value(article, "raw_text")[:12000]
    if not _SOURCE_SARCASM.search(source):
        return ""
    for sentence in _parts(str(final_text or "")):
        if _OUTPUT_EDITORIAL_VOICE.search(sentence) and not _ATTRIBUTION.search(sentence):
            return "MONITORING_SOURCE_SARCASM_ADOPTED"
    return ""


def monitoring_unattributed_editorial_money_reason(article: Any, final_text: str) -> str:
    """Do not promote an ironic newsroom budget claim into confirmed funding.

    This only covers a numeric sum that appears inside the source publisher's
    sarcastic sentence, with no independent nonsarcastic source declaration.
    """
    source_parts = _parts(_value(article, "raw_text")[:12000])
    ironic = [
        p for p in source_parts if _SOURCE_SARCASM.search(p) and _MONEY_CLAIM.search(p)
    ]
    if not ironic:
        return ""
    plain = [p for p in source_parts if not _SOURCE_SARCASM.search(p) and "?" not in p]
    for out in _parts(str(final_text or "")):
        if _ATTRIBUTION.search(out):
            continue
        for match in _MONEY_CLAIM.finditer(out):
            amount = match.group(1).replace(",", ".")
            if not any(
                x.group(1).replace(",", ".") == amount
                for p in ironic for x in _MONEY_CLAIM.finditer(p)
            ):
                continue
            if any(
                x.group(1).replace(",", ".") == amount
                for p in plain for x in _MONEY_CLAIM.finditer(p)
            ):
                continue
            return "MONITORING_SOURCE_EDITORIAL_MONEY_AS_FACT"
    return ""


def monitoring_source_stance_reason(article: Any, final_text: str) -> str:
    return (
        monitoring_editorial_question_reason(article, final_text)
        or monitoring_unattributed_sarcasm_reason(article, final_text)
        or monitoring_unattributed_editorial_money_reason(article, final_text)
    )


MONITORING_STANCE_INSTRUCTION = (
    "\nФАКТ VS КОМЕНТАР ДЖЕРЕЛА: відділяй підтверджений факт від "
    "іронії, сарказму, авторської оцінки, чуток і риторичних питань "
    "редакції Telegram-джерела. Знак «?» не є підтвердженням події. "
    "Не перетворюй запитання «перейшли, бо стало некомфортно?» на "
    "ствердження «перейшли, бо стало некомфортно». "
    "Не привласнюй саркастичні висновки («оце так робота») голосом "
    "нашого каналу. Передавай лише підтверджені події/цифри; "
    "оцінку, непідтверджену суму бюджету чи мотив не стверджуй як факт. "
    "Якщо коментар важливий, точно атрибутуй його автору як думку "
    "чи риторичне запитання; якщо не потрібен, опусти. "
    "Не роби висновків із насмішки, мемів або чужих реплік.\n"
)
