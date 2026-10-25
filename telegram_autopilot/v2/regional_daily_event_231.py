"""2.2.31 conservative identity for regional daily attack/casualty reports.

Only original publisher facts count. A follow-up with another confirmed casualty
total is not a duplicate, and a single attack in one town is not a daily digest.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import re
from typing import Any

_MONTHS = {
    "січня": 1, "лютого": 2, "березня": 3, "квітня": 4,
    "травня": 5, "червня": 6, "липня": 7, "серпня": 8,
    "вересня": 9, "жовтня": 10, "листопада": 11, "грудня": 12,
}
_DATE = re.compile(
    r"(?iu)\b(\d{1,2})\s+(січня|лютого|березня|квітня|травня|червня|"
    r"липня|серпня|вересня|жовтня|листопада|грудня)\b"
)
_URL = re.compile(r"https?://\S+", re.I)
_REGION = re.compile(r"(?iu)запорі(?:жж|зьк)")
_SCOPE = re.compile(r"(?iu)(?:област\w*|запорізьк\w*\s+район\w*|"
                    r"запоріжж\w*\s+та\s+(?:запорізьк\w*\s+)?район\w*)")
_DAILY = re.compile(
    r"(?iu)(?:\b(?:упродовж|протягом|впродовж)\s+(?:минулої\s+)?доби\b|"
    r"\bза\s+(?:минул\w*|попередн\w*)?\s*добу\b|"
    r"\bвчора\b|\bпідсумк\w*\s+(?:атак\w*|обстріл\w*)|"
    r"\bза\s+\d{1,2}\s+жовтня\b|\bподробиц\w*\s+удар\w*)"
)
_ATTACK = re.compile(r"(?iu)\b(?:атак\w*|удар\w*|обстріл\w*|обстріля\w*)")
_INJURED = re.compile(r"(?iu)(?:поран\w*|постраждал\w*|травм\w*|дістал\w*\s+поранен\w*)")
_AGE = re.compile(r"(?iu)(?<!\d)(\d{1,2})[\-–‑]річн\w*")
_STRIKES = re.compile(
    r"(?iu)\b(?:завдал\w*\s+|скоєно\s+)?(\d{2,4})\s+"
    r"(?:ворож\w*\s+)?(?:удар\w*|атак\w*|обстріл\w*)\b"
)
_COUNT_WORDS = {
    "одна": 1, "один": 1, "одну": 1, "двоє": 2, "дві": 2,
    "два": 2, "троє": 3, "три": 3, "четверо": 4, "чотири": 4,
    "п'ятеро": 5, "п’ятеро": 5, "п'ять": 5, "п’ять": 5,
    "шестеро": 6, "шість": 6, "семеро": 7, "сім": 7,
    "восьмеро": 8, "вісім": 8, "дев'ятеро": 9, "дев’ятеро": 9,
    "десятеро": 10, "десять": 10,
}
_NUMBER = r"(?:\d{1,2}|" + "|".join(re.escape(k) for k in _COUNT_WORDS) + r")"
_CASUALTIES = re.compile(
    r"(?iu)\b(?:" + _NUMBER + r")\b\s+"
    r"(?:люд\w*|особ\w*|жін\w*|чоловік\w*|дитин\w*)"
    r"(?:\s+\w+){0,2}\s+"
    r"(?:поранен\w*|постраждал\w*|дістал\w*\s+поранен\w*|"
    r"отримал\w*\s+поранен\w*)\b|"
    r"\b(?:поранен\w*|постраждал\w*)\s+(?:" + _NUMBER + r")\b(?![-–‑]річн)"
)
_NUMBER_FIRST = re.compile(r"(?iu)^\s*(" + _NUMBER + r")\b")
_NUMBER_LAST = re.compile(r"(?iu)\b(" + _NUMBER + r")\s*$")
_UPDATE = re.compile(
    r"(?iu)\b(?:уточнил\w*|оновил\w*|оновлен\w*|"
    r"скоригувал\w*|виправил\w*|додатков\w*\s+підтвердил\w*|"
    r"кількість\s+поранен\w*\s+(?:зросл\w*|збільшил\w*)|"
    r"стало\s+відомо\s+про\s+ще)\b"
)


def _get(row: Any, name: str) -> str:
    try:
        result = row[name]
    except (KeyError, IndexError, TypeError):
        result = getattr(row, name, "")
    return str(result or "")


def _source(row: Any) -> str:
    # Ignore AI-created final_text and editorial labels.
    # Raw original body takes precedence. Joining a truncated title to the body
    # can fabricate adjacent tokens (e.g. a date becomes a casualty count).
    source = _get(row, "raw_text") or _get(row, "title")
    return _URL.sub(" ", source[:12000]).casefold()


def _source_time(row: Any) -> datetime | None:
    # Discovered-at and Telegram send time cannot date the ORIGINAL event.
    raw = _get(row, "source_published_at")
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return value if value.tzinfo else None
    except ValueError:
        return None


def _casualty_number(text: str) -> int | None:
    matches = []
    for m in _CASUALTIES.finditer(text):
        token = _NUMBER_FIRST.search(m.group()) or _NUMBER_LAST.search(m.group())
        if not token:
            continue
        term = token.group(1).casefold()
        n = int(term) if term.isdigit() else _COUNT_WORDS.get(term)
        if n is not None and 0 < n < 40:
            matches.append(n)
    if not matches:
        return None
    return matches[0] if len(set(matches)) == 1 else None


def regional_daily_facts(row: Any) -> dict[str, Any]:
    text = _source(row)
    if not (_REGION.search(text) and _SCOPE.search(text) and _DAILY.search(text)
            and _ATTACK.search(text) and _INJURED.search(text)):
        return {}
    published = _source_time(row)
    if published is None:
        return {}
    days = {(int(m.group(1)), _MONTHS[m.group(2)]) for m in _DATE.finditer(text)}
    if len(days) > 1:
        return {}  # Multiple reporting days, no single event identity.
    if days:
        day, month = next(iter(days))
        try:
            year = published.year
            report_day = date(year, month, day)
            if report_day > published.date() + timedelta(days=2):
                report_day = date(year-1, month, day)
        except ValueError:
            return {}
    elif re.search(r"(?iu)\b(?:вчора|минул\w*\s+добу|попередн\w*\s+добу|упродовж\s+доби|протягом\s+доби|за\s+добу)\b", text):
        report_day = (published - timedelta(days=1)).date()
    else:
        return {}

    strike_totals = set()
    for match in _STRIKES.finditer(text):
        # Distinguish aggregate daily count from rockets/UAV/airstrike breakdown.
        prefix = text[max(0, match.start()-105):match.start()]
        if re.search(r"(?iu)(?:упродовж|протягом|за|впродовж)\s+(?:минулої\s+)?доби|загалом", prefix):
            strike_totals.add(int(match.group(1)))
    strikes = next(iter(strike_totals)) if len(strike_totals) == 1 else None
    ages = sorted({int(x) for x in _AGE.findall(text) if 0 < int(x) < 100})
    injured = _casualty_number(text)
    # Listing four injured people with four distinct ages can corroborate the
    # aggregate, but cannot override an explicit different aggregate number.
    if injured is None and len(ages) >= 3:
        injured = len(ages)
    if strikes is None and len(ages) < 2:
        return {}  # A single local attack is not a daily regional digest.
    return {
        "family": "regional_daily_attacks",
        "place": "zaporizhzhia_oblast",
        "target": "regional_daily_summary",
        "report_day": report_day.isoformat(),
        "strikes": strikes,
        "injured": injured,
        "ages": ages,
        "correction": bool(_UPDATE.search(text)),
    }


def regional_daily_relation_facts(now: dict[str, Any], prior: dict[str, Any]) -> str:
    if not now or not prior:
        return ""
    if now.get("family") != "regional_daily_attacks" or prior.get("family") != "regional_daily_attacks":
        return ""
    if (now["place"], now["report_day"]) != (prior["place"], prior["report_day"]):
        return ""
    left_count, right_count = now.get("injured"), prior.get("injured")
    left_strikes, right_strikes = now.get("strikes"), prior.get("strikes")
    overlap = len(set(now.get("ages", [])) & set(prior.get("ages", [])))
    if left_count is not None and right_count is not None and left_count != right_count:
        if now.get("correction") and (
            (left_strikes is not None and left_strikes == right_strikes) or overlap >= 2
        ):
            return "UPDATE"
        return ""  # Never discard an unconfirmed changed-casualty announcement.
    if left_strikes is not None and right_strikes is not None and left_strikes != right_strikes:
        if now.get("correction") and left_count == right_count and left_count is not None:
            return "UPDATE"
        return ""
    # Strong duplicate: matching full regional tally plus same casualty total,
    # or the same set of 3+ independently source-named injured victim ages.
    if left_strikes is not None and left_strikes == right_strikes and (
        (left_count is not None and left_count == right_count) or overlap >= 2
    ):
        return "DUPLICATE"
    if overlap >= 3 and (left_count is None or right_count is None or left_count == right_count):
        return "DUPLICATE"
    # Bridge a police victim-by-victim report to a later OVA aggregate with
    # one shared age ONLY if both list the same four injured and one has tally.
    if overlap >= 1 and left_count is not None and left_count == right_count and (
        left_strikes is not None or right_strikes is not None
    ) and left_count >= 3:
        return "DUPLICATE"
    return ""


def regional_daily_relation(current: Any, candidate: Any) -> str:
    a, b = regional_daily_facts(current), regional_daily_facts(candidate)
    if not a or not b:
        return ""
    ta, tb = _source_time(current), _source_time(candidate)
    if ta is None or tb is None or abs(ta - tb) > timedelta(hours=18):
        return ""
    return regional_daily_relation_facts(a, b)
