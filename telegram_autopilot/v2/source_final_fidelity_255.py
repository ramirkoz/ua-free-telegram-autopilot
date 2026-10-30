"""v2.2.55: high-confidence SOURCE -> FINAL factual-inversion guards.

This is not general NLI. It blocks only source-provable contradictions from
real 2.2.54 operator posts, not editorial style or unknown extra facts.
No network/AI work and no changes to source or delivery policy.
"""
from __future__ import annotations

import re
from typing import Any

_WORD = r"[а-яіїєґa-z]"
_EVENT_WORDS = r"(?:удар\w*|обстріл\w*|атак\w*|вибух\w*|загинул\w*|загинув\w*|поранен\w*)"
_ZP_CITY = re.compile(r"(?iu)\b(?:у|в)\s+Запоріжжі\b")
_ZP_RESIDENTS = re.compile(
    r"(?iu)\b(?:мешканц\w*|жител\w*|уродженц\w*)\s+(?:міста\s+)?Запоріжжя\b"
)
_ZP_EXPLICIT_EVENT = re.compile(
    r"(?iu)(?:"
    r"(?:у|в)\s+Запоріжжі\b.{0,72}\b(?:влуч\w*|атак\w*|удар\w*|обстріл\w*|вибух\w*|загинул\w*|загинув\w*|поранен\w*)"
    r"|(?:влуч\w*|атак\w*|удар\w*|обстріл\w*|вибух\w*)\b.{0,72}\b(?:у|в)\s+Запоріжжі"
    r")"
)
_ZP_DEATH_LOCATION = re.compile(
    r"(?iu)\b(?:у|в)\s+Запоріжжі\b.{0,94}"
    r"(?:\b\d+\s+\w+\s+)?\b(?:загинул\w*|загинув\w*|поранен\w*|"
    r"внаслідок\s+(?:російськ\w*\s+)?удар\w*|після\s+удар\w*)"
)
_TRAIN_ROUTE = re.compile(r"(?iu)\b(?:потяг\w*|поїзд\w*|рейс\w*)\s+Дніпро\s*[-—–]\s*Запоріжжя")
_OLD_VIDEO = re.compile(
    r"(?iu)(?:\b(?:відео|відеозапис\w*|ролик\w*|кадр\w*)\b.{0,180}"
    r"\b(?:не\s+сьогоднішн\w*|учорашн\w*|вчорашн\w*|стар\w*|архівн\w*)\b|"
    r"\b(?:не\s+сьогоднішн\w*|учорашн\w*|вчорашн\w*|стар\w*|архівн\w*)\b.{0,120}"
    r"\b(?:відео|відеозапис\w*|ролик\w*|кадр\w*)\b)"
)
_NEW_BLAST = re.compile(
    r"(?iu)(?:\b(?:у|в)\s+Запоріжжі\b.{0,60}\b(?:вранці|зранку|сьогодні)\b"
    r"|\b(?:вранці|зранку|сьогодні)\b.{0,65}\b(?:у|в)\s+Запоріжжі\b)"
    r".{0,100}\b(?:пролунал\w*\s+вибух\w*|ставс\w*\s+вибух\w*|"
    r"були\s+вибух\w*|відбул\w*\s+вибух\w*)"
)
_NEW_BLAST_INVERT = re.compile(
    r"(?iu)\b(?:у|в)\s+Запоріжжі\b.{0,65}\b(?:пролунал\w*\s+вибух\w*|"
    r"ставс\w*\s+вибух\w*|були\s+вибух\w*).{0,65}\b(?:вранці|зранку|сьогодні)\b"
)
_BLAST_SOURCE = re.compile(r"(?iu)\b(?:вибух\w*|прильот\w*|удар\w*|обстріл\w*)")
_OLD_REFERENCE = re.compile(r"(?iu)\b(?:учора|вчора|позавчора|раніше|архівн\w*|на\s+(?:старому|цьому)\s+відео)\b")

_PERCENT_INCREASE_EN = re.compile(
    r"(?i)\b(?:by\s+|rise\s+(?:of|by)\s+|increase\s+(?:of|by)\s+)?"
    r"(\d{1,3}(?:[.,]\d+)?)\s*(?:percent|%)\s+(?:more|higher|increase)\b"
    r"|\b(?:increase|rise|grow|higher|more)\b.{0,34}\bby\s+(\d{1,3}(?:[.,]\d+)?)\s*(?:percent|%)"
)
_PERCENT_INCREASE_UK = re.compile(
    r"(?iu)\b(?:на\s+(\d{1,3}(?:[.,]\d+)?)\s*%(\s+більше)?|"
    r"(\d{1,3}(?:[.,]\d+)?)\s*%\s+(?:вищ\w*|більш\w*))"
)
_PERCENT_TO_UK = re.compile(r"(?iu)\bдо\s+(\d{1,3}(?:[.,]\d+)?)\s*%")
_PERCENT_TO_EN = re.compile(r"(?i)\b(?:to|reach|reaching)\s+(\d{1,3}(?:[.,]\d+)?)\s*(?:percent|%)")
_SAME_METRIC = re.compile(
    r"(?iu)(?:викид\w*|еміс\w*|pollution|emissions|carbon|"
    r"кількіст\w*|частк\w*|виробництв\w*)"
)
_QUALIFIERS = re.compile(r"(?iu)\b(?:не\s+най|не\s+були\s+най|не\s+є\s+най)\b")
_MAX_OUTPUT = re.compile(
    r"(?iu)\b(?:найінтенсивніш\w*|найчастіш\w*|найбільш\w*\s+численн\w*)"
    r".{0,80}\b(?:рсзв|реактивн\w*)"
    r"|\b(?:рсзв|реактивн\w*)\b.{0,70}\b(?:найінтенсивніш\w*|найчастіш\w*)"
)
_ROCKET_COUNT = re.compile(r"(?iu)\b(?:\d{1,3}\s*(?:раз\w*|удар\w*|обстріл\w*)\s+.{0,80}\bрсзв|"
                           r"\b(\d{1,3})\s*(?:раз\w*|удар\w*|обстріл\w*)\s+.{0,40}\bрсзв)")
_DRONE_COUNT = re.compile(
    r"(?iu)\b(\d{2,4})\s*(?:раз\w*|атак\w*|удар\w*)\s+"
    r"(?:\S+\s+){0,3}(?:бпла|безпілотник\w*|дрон\w*)"
    r"|\b(?:бпла|безпілотник\w*|дрон\w*)\s+"
    r"(?:\S+\s+){0,4}(\d{2,4})\s*(?:раз\w*|удар\w*|атак\w*)"
)


def _read(article: Any, field: str) -> str:
    try:
        v = article[field]
    except (TypeError, IndexError, KeyError):
        v = getattr(article, field, "")
    return str(v or "")


def _number(value: str) -> str:
    return value.replace(",", ".").strip()


def _percent_increase(source: str) -> set[str]:
    found: set[str] = set()
    for pattern in (_PERCENT_INCREASE_EN, _PERCENT_INCREASE_UK):
        for match in pattern.finditer(source):
            for value in match.groups():
                if value and re.fullmatch(r"\d{1,3}(?:[.,]\d+)?", value):
                    found.add(_number(value))
    return found


def _explicit_to(source: str) -> set[str]:
    return {
        _number(match.group(1))
        for pattern in (_PERCENT_TO_UK, _PERCENT_TO_EN)
        for match in pattern.finditer(source)
    }


def source_final_fidelity_issues(article: Any, final_text: str) -> tuple[str, ...]:
    """Return only high-confidence SOURCE-bounded contradictions.

    SOURCE is the immutable source raw text. Titles are intentionally excluded
    from factual corroboration: a Telegram title may be a scraped teaser.
    """
    source = _read(article, "raw_text")[:18000]
    out = str(final_text or "")[:8000]
    if not source.strip() or not out.strip():
        return ()
    issues: list[str] = []

    # Residents of a city and a *route ending there* do not prove that an
    # attack took place in that city. Only veto the exact observed collision.
    if (
        _ZP_RESIDENTS.search(source)
        and _TRAIN_ROUTE.search(source)
        and not _ZP_EXPLICIT_EVENT.search(source)
        and _ZP_DEATH_LOCATION.search(out)
    ):
        issues.append("FACT_EVENT_LOCATION_VS_RESIDENCE_255")

    # A fact-check that a circulating video is old cannot create a *new*
    # morning incident. A faithful recap of what an old video depicts is fine.
    if (
        _OLD_VIDEO.search(source)
        and not _BLAST_SOURCE.search(source)
        and (_NEW_BLAST.search(out) or _NEW_BLAST_INVERT.search(out))
        and not _OLD_REFERENCE.search(out)
    ):
        issues.append("FACT_ARCHIVE_VIDEO_NEW_EVENT_255")

    # Source explicitly says '+42%' vs. previous baseline. 'to 42%' changes
    # the mathematical operator and must never be inferred from that SOURCE.
    increased = _percent_increase(source)
    if increased and _SAME_METRIC.search(source) and _SAME_METRIC.search(out):
        to_in_source = _explicit_to(source)
        for match in _PERCENT_TO_UK.finditer(out):
            value = _number(match.group(1))
            if value in increased and value not in to_in_source:
                issues.append("FACT_PERCENT_BY_TO_INVERSION_255")
                break

    # The local-news operator described five MLRS strikes as "most intense"
    # even though the same source listed 624 drone strikes. Only this
    # unmistakable numerical category reversal is covered here.
    if _MAX_OUTPUT.search(out) and not _QUALIFIERS.search(out):
        if re.search(r"(?iu)\bрсзв\b", source) and re.search(r"(?iu)\b(?:бпла|безпілотник\w*|дрон\w*)\b", source):
            drone_counts = [int(x or y) for m in _DRONE_COUNT.finditer(source) for x, y in [m.groups()]]
            # Require the source to contain five (or another 1-9 count) for MLRS.
            rocket_counts = [
                int(m.group(1)) for m in re.finditer(
                    r"(?iu)\b(\d{1,2})\s*(?:раз\w*|удар\w*|обстріл\w*)"
                    r".{0,100}\bрсзв", source
                )
            ]
            if rocket_counts and drone_counts and min(rocket_counts) < max(drone_counts):
                issues.append("FACT_UNSUPPORTED_CATEGORY_SUPERLATIVE_255")

    return tuple(dict.fromkeys(issues))


SOURCE_FINAL_FIDELITY_RULE_255 = (
    "SOURCE → DRAFT → FINAL | ФАКТИЧНА ТОЧНІСТЬ v2.2.55: "
    "«мешканці Запоріжжя» означає місце проживання людей, "
    "а НЕ місце удару. Поїзд «Дніпро — Запоріжжя» є маршрутом, "
    "а НЕ доказом місця події. Коли SOURCE не встановлює місце удару, "
    "не дописуй його; не переносити інцидент до міста проживання жертв. "
    "Старе або вчорашнє ВІДЕО не підтверджує вибухів сьогодні: "
    "не перетворюй спростування на повідомлення про новий вибух. "
    "Англійське '42 percent MORE / increase BY 42%' означає "
    "«НА 42% більше», а не «ДО 42%». "
    "Не називай п'ять ударів РСЗВ найінтенсивнішими, якщо SOURCE "
    "називає сотні атак БпЛА і не робить такого порівняння. "
    "Не плутай число по всьому місту з числом окремого відділення; "
    "уточнюй обсяг кожної статистики, якщо SOURCE це дозволяє. "
    "У науці відділяй висновки на нематодах від досліджень людських "
    "клітин; не обіцяй продовження життя людям без людських доказів. "
    "Не визначай «сьогодні/завтра» для вказаних годин, "
    "якщо SOURCE не дає конкретної дати. "
    "Під час виправлення можна прибрати непідтверджену деталь, "
    "але НЕ можна домислити інший факт."
)
