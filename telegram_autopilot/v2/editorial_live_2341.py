"""2.3.41 QA: targeted source-evidenced decisions from owner LIVE review.

The source, not the generated post, defines the underlying event. No Data,
Telegram, or provider calls are made here.
"""
from __future__ import annotations

from datetime import datetime
import re
from typing import Any


def _f(row: Any, key: str) -> str:
    try:
        return str(row[key] or "")
    except (KeyError, IndexError, TypeError):
        return str(getattr(row, key, "") or "")


_TOTAL_ATTACKS = re.compile(r"(?iu)\b(\d{2,4})\s+(?:удар(?:ів|и)?|обстріл(?:ів|и)?)\b")
_SETTLEMENTS = re.compile(r"(?iu)\b(\d{1,3})\s+населен\w*\s+пункт\w*")
_COUNT_WORDS = (
    r"\d{1,2}|одна|один|одну|двоє|двох|дві|два|троє|три|трьох|"
    r"четверо|чотири|п.ятеро|п.ять|шестеро|шість|шестох|"
    r"семеро|сім|семох|восьмеро|вісім|дев.ятеро|дев.ять|десятеро|десять"
)
_DEAD = re.compile(r"(?iu)\b(" + _COUNT_WORDS + r")\s+людин\w*\s+загинул\w*")
_WOUNDED = re.compile(r"(?iu)\b(" + _COUNT_WORDS + r")\s+(?:\w+\s+){0,3}поран\w*")
_COUNT_NORMALIZE = {
    "одна": "1", "один": "1", "одну": "1", "двоє": "2", "двох": "2", "два": "2", "дві": "2",
    "троє": "3", "три": "3", "трьох": "3", "четверо": "4", "чотири": "4",
    "п'ятеро": "5", "п’ятеро": "5", "п'ять": "5", "п’ять": "5",
    "шестеро": "6", "шість": "6", "шестох": "6", "семеро": "7", "сім": "7", "семох": "7",
    "восьмеро": "8", "вісім": "8", "дев'ятеро": "9", "дев’ятеро": "9",
    "дев'ять": "9", "дев’ять": "9", "десятеро": "10", "десять": "10",
}


def _count(word: str) -> str:
    return _COUNT_NORMALIZE.get(word.casefold(), word)


_NUMERIC = re.compile(r"(?<![\w])\d{2,4}(?![\w])")
_REPORT_DATE = re.compile(r"(?iu)\b(\d{1,2})\s+(січня|лютого|березня|квітня|травня|червня|липня|серпня|вересня|жовтня|листопада|грудня)\b")
_LINK = re.compile(r"https?://\S+", re.I)


def _report(row: Any) -> tuple[str, str, str, str, set[str], str] | None:
    # Original source-owned text only. Strip links before numeric extraction.
    raw = _LINK.sub(" ", _f(row, "raw_text")[:6000])
    title = _LINK.sub(" ", _f(row, "title")[:1000])
    text = title + " " + raw
    killed = _DEAD.search(text)
    hurt = _WOUNDED.search(text)
    if not (re.search(r"(?iu)запоріз\w*\s+област\w*", text)
            and killed and hurt):
        return None
    total = _TOTAL_ATTACKS.search(text)
    settlements = _SETTLEMENTS.search(text)
    if not (total and settlements):
        return None
    breakdown = set(_NUMERIC.findall(text)) - {total.group(1), settlements.group(1)}
    # Require two shared breakdown counts besides the total and settlement count.
    explicit_day = _REPORT_DATE.search(raw)
    day = (explicit_day.group(1) + " " + explicit_day.group(2)) if explicit_day else ""
    return total.group(1), settlements.group(1), _count(killed.group(1)), _count(hurt.group(1)), breakdown, day


def same_zaporizhzhia_daily_attack_bulletin_2341(current: Any, prior: Any) -> bool:
    """Same published daily report, not just a similar raid or same subject."""
    a, b = _report(current), _report(prior)
    if a is None or b is None:
        return False
    if a[:4] != b[:4] or len(a[4] & b[4]) < 2:
        return False
    if a[5] and b[5] and a[5] != b[5]:
        return False
    ad = _f(current, "source_published_at") or _f(current, "published_at")
    bd = _f(prior, "source_published_at") or _f(prior, "published_at")
    if ad and bd:
        try:
            at = datetime.fromisoformat(ad.replace("Z", "+00:00"))
            bt = datetime.fromisoformat(bd.replace("Z", "+00:00"))
            if abs((at - bt).total_seconds()) > 18 * 3600:
                return False
            if not a[5] or not b[5]:
                if at.date() != bt.date():
                    return False
        except ValueError:
            return False
    return True


_STANDARD_RECIPE = re.compile(
    r"(?iu)\b(?:recipe|recipes|how\s+to\s+make\s+(?:a|the|your)?\s*"
    r"(?:sandwich|hoagie|meal|dinner|dessert)|рецепт\w*|як\s+приготува\w*)\b"
)
_RECIPE_STEPS = re.compile(r"(?iu)\b(?:ingredients|step\s*[1-9]|preheat|bake\s+for|cook\s+until|assembling\s+the\s+sandwich|інгредієнт\w*|крок\s*1)\b")
_CREATIVE_RECIPE_EXCEPTION = re.compile(
    r"(?iu)\b(?:new\s+(?:product|device|packaging|prototype|invention|material)|"
    r"(?:original|viral|unusual|creative)\s+(?:ad\s+campaign|marketing\s+campaign)|"
    r"robot(?:ic)?\s+(?:chef|cooking)|food[ -]tech\s+invention|"
    r"нов\w*\s+(?:продукт\w*|пристр\w*|пакуван\w*|винах\w*)|"
    r"рекламн\w*\s+кампані\w*)\b"
)


def creative_ordinary_cooking_recipe_reason_2341(article: Any) -> str:
    """Source-only veto for ordinary cooking instructions, not food innovation."""
    title, body = _f(article, "title")[:1000], _f(article, "raw_text")[:6000]
    if (_STANDARD_RECIPE.search(title) and _RECIPE_STEPS.search(body)
            and not _CREATIVE_RECIPE_EXCEPTION.search(title + " " + body[:1500])):
        return "CREATIVE_ORDINARY_COOKING_RECIPE_NOT_NEWS_2341"
    return ""
