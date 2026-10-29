"""2.2.52: source-bounded news completeness and factual-update QA.

This module never fetches untrusted third-party URLs or invents missing data.
It fails closed only for strongly recognizable linked teasers that promise
practical answers but do not contain them; existing good reports stay eligible.
"""
from __future__ import annotations

import re
from typing import Any

_TEASER = re.compile(r"(?iu)\bдетальніше\s*:\s*https?://")
_RENAME = re.compile(r"(?iu)(?:перейменува\w*\s+(?:\S+\s+){0,4}вулиц\w*|які\s+нові\s+назви)")
_NEW_NAME = re.compile(
    r"(?iu)\b(?:тепер\s+назива\w*|відтепер\s+назива\w*|"
    r"стала\s+(?:вулиц\w*\s+)?|став\s+(?:вулиц\w*\s+)?|"
    r"перейменува\w*\s+на\s+|змінила\s+назву\s+на\s+|"
    r"нов\w*\s+назв\w*\s*[:—–-])"
)
_WATER = re.compile(r"(?iu)(?:відключил\w*|відключенн\w*|обмежил\w*)\s+(?:\S+\s+){0,4}вод\w*|водопостачанн\w*")
_ADDRESS_PROMISE = re.compile(r"(?iu)(?:повн\w*\s+перелік\s+адрес|за\s+десятками\s+адрес)")
_ADDRESS = re.compile(
    r"(?iu)\b(?:вул\.?|вулиц\w*|просп\.?|проспект\w*|пров\.?|"
    r"провул\w*|бульвар\w*|площ\w*)\s+"
    r"(?:імені\s+)?[«\"']?[А-ЯІЇЄҐA-Z][А-ЯІЇЄҐа-яіїєґA-Za-z0-9'’.-]{2,}"
)
_UPDATED_WOUNDED = re.compile(
    r"(?iu)(?:\bдо\s+(\d{1,4})\s+зросла\s+кількість\s+поранен\w*|"
    r"\bкількість\s+поранен\w*\s+зросла\s+до\s+(\d{1,4}))"
)
_OLD_WOUNDED = re.compile(
    r"(?iu)\b(\d{1,4})\s+(?:отримал\w*|дістал\w*|зазнал\w*)\s+пораненн\w*|"
    r"\b(\d{1,4})\s+поранен\w*"
)
_EARLIER = re.compile(r"(?iu)\b(?:спочатку|раніше|первинно|за\s+першими\s+даними|попередньо)\b")
_EDITOR_VOICE = re.compile(
    r"(?i)\b(?:I['’]?m|I\s+(?:think|feel|believe|for one)|"
    r"in\s+my\s+(?:view|opinion)|it\s+seems|it\s+feels|"
    r"seems\s+(?:that|to)|my\s+take)\b"
)
_EXPLICIT_BRAND_INTENT = re.compile(
    r"(?i)\b(?:intentionally|deliberately|purposefully|consciously|"
    r"brand\s+(?:said|stated|confirmed)|company\s+(?:said|stated|confirmed))\b|"
    r"(?iu)\b(?:свідомо|навмисно|цілеспрямовано)\b"
)
_FINAL_INTENT = re.compile(r"(?iu)\b(?:свідомо|навмисно|цілеспрямовано)\b")
_ATTRIBUTED_OPINION = re.compile(
    r"(?iu)\b(?:на\s+думку|за\s+оцінкою|як\s+вважає|"
    r"за\s+словами\s+(?:автора|авторки|оглядача)|на\s+погляд)\b"
)


def _read(article: Any, key: str) -> str:
    try:
        value = article[key]
    except (KeyError, IndexError, TypeError):
        value = getattr(article, key, "")
    return str(value or "")


def source_completeness_issue(article: Any) -> str:
    """Detect *proven* incomplete external-link teasers, not short real alerts.

    A headline question alone is not enough for a veto: it must carry an
    explicit outbound 'Детальніше:' teaser marker and lack its promised facts.
    The source may be Ukrainian or English, but these guards only inspect
    the two observed Ukrainian municipal headline families.
    """
    raw = _read(article, "raw_text")
    title = _read(article, "title")
    heading = title[:430]
    if not _TEASER.search(raw):
        return ""
    if _RENAME.search(heading) and not _NEW_NAME.search(raw):
        return "SOURCE_DETAIL_MISSING_252: анонс перейменування не містить нових назв"
    if _WATER.search(heading) and _ADDRESS_PROMISE.search(heading) and not _ADDRESS.search(raw):
        return "SOURCE_DETAIL_MISSING_252: анонс відключення води не містить обіцяних адрес"
    return ""


def final_reader_issue(article: Any, final: str) -> str:
    """Prevent narrow provable harmful rewrites, without changing text.

    In an updated casualty report the latest number must not appear beside an
    older number as a simultaneous current total. A source editorial opinion
    is not a verified brand decision.
    """
    source_issue = source_completeness_issue(article)
    if source_issue:
        return source_issue

    raw = _read(article, "raw_text")
    title = _read(article, "title")
    output = str(final or "")
    updates = _UPDATED_WOUNDED.findall(raw)
    if updates:
        latest = int(next(value for value in updates[-1] if value))
        if 0 < latest < 1000:
            for match in _OLD_WOUNDED.finditer(output):
                earlier = int(match.group(1) or match.group(2))
                if earlier >= latest or earlier == 0:
                    continue
                # Clear 'initially 5, later 10' chronology is entirely valid.
                sentence_start = max(
                    output.rfind(".", 0, match.start()),
                    output.rfind("\n", 0, match.start()),
                ) + 1
                if _EARLIER.search(output[sentence_start:match.start()]):
                    continue
                return (
                    "OUTDATED_CASUALTY_COUNT_252: фінальний текст подає попередню "
                    "кількість поранених як поточну, хоча SOURCE містить оновлення"
                )

    if (
        _EDITOR_VOICE.search(raw)
        and _FINAL_INTENT.search(output)
        and not _EXPLICIT_BRAND_INTENT.search(raw)
        and not _ATTRIBUTED_OPINION.search(output)
    ):
        # A reviewer's impression cannot be upgraded to the company's motive.
        if re.search(r"(?i)\b(?:brand|company|advertis|campaign)\b", title + " " + raw[:1500]):
            return (
                "UNATTRIBUTED_BRAND_INTENT_252: оцінку журналіста подано "
                "як підтверджений свідомий намір компанії"
            )
    return ""


READER_COMPLETENESS_RULE_252 = (
    "2.2.52 РЕДАКЦІЙНА ПОВНОТА: Якщо заголовок обіцяє нові назви, конкретні "
    "адреси, строк або умови, надай саму відповідь з SOURCE, а не фразу "
    "«повний перелік опубліковано». Коли короткий Telegram-анонс має лише "
    "«Детальніше» і не містить потрібних відомостей, НЕ додумуй деталей. "
    "Якщо в SOURCE зазначено, що число поранених ЗРОСЛО, почни з "
    "останнього підтвердженого числа; старе вкажи лише як попередні дані "
    "з явною хронологією. Не називай авторське враження оглядача "
    "свідомим рішенням бренду. Для складної науки спочатку поясни "
    "результат простими словами, потім, за потреби, механізм."
)
