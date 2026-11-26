"""2.3.13: lossless cleanup of joined Telegram schedule rows before AI.

Only a clock time immediately followed by a visibly numbered next schedule
row is separated. Never repair a malformed AI output or infer new hours.
Original operator Data/source text remains immutable.
"""
from __future__ import annotations

import re


# Telegram text extraction can join "22:30" and next row "1.2:" into
# "22:301.2:".  The second colon is critical evidence of a new row.
# This is NOT a general-purpose numeric spellchecker.
_JOINED_SCHEDULE_ROW = re.compile(
    r"(?<!\d)((?:[01]?\d|2[0-4]):[0-5]\d)(?=[1-9]\.[1-9](?=\s*[:：]))"
)
_NUMBER_ATOM = re.compile(
    r"(?<!\w)(?:\d{1,3}(?:[ \u00a0]\d{3})+|\d+(?::\d+){1,2}|\d+(?:[.,]\d+)+|\d+)(?!\w)"
)
_TIME_ATOM = re.compile(r"(?<!\w)(?:[01]?\d|2[0-4]):[0-5]\d(?!\w)")
_SCHEDULE_CONTEXT = re.compile(
    r"(?iu)\b(?:графік\w*|відключенн\w*|розклад\w*|погодинн\w*|schedule\w*)\b"
)

STRUCTURED_SCHEDULE_WRITER_RULE_2313 = (
    "ЧИСЛОВІ ГРАФІКИ: у SOURCE можуть бути склеєні кінці рядків "
    "на кшталт «22:301.2:», це 22:30 і початок черги 1.2. "
    "Зберігай тільки точно підтверджені години, дату, чергу та напрям зміни. "
    "Не переписуй усю велику таблицю заради довжини поста. "
    "За великого графіка передай найважливіші підтверджені зміни і "
    "згадай, що повний графік міститься в першоджерелі. "
    "Не вигадуй часових проміжків, не склеюй дві сусідні години, "
    "не додавай числа й не замінюй 24:00 на 00:00.\n"
)


def restore_joined_schedule_rows(text: str) -> str:
    """Insert only provable boundaries. Does not change numeric values."""
    return _JOINED_SCHEDULE_ROW.sub(r"\1\n", str(text or ""))


def numeric_atoms(text: str) -> set[str]:
    """Compare independently anchored numbers, times and dates.

    Unlike a greedy punctuation/whitespace matcher, this never merges
    '00:00 – 05:00, 09:00' into a fabricated single numeric token.
    Non-numeric model IDs remain excluded. Malformed '21:3041' stays
    an unsupported atom rather than being silently repaired.
    """
    clean = re.sub(r"https?://\S+", "", str(text or ""))
    clean = restore_joined_schedule_rows(clean)
    return {
        re.sub(r"[\s,_]", "", match.group())
        for match in _NUMBER_ATOM.finditer(clean)
        if match.group()
    }


def schedule_guidance(text: str) -> str:
    """Only time-rich schedule sources get extra AI guidance."""
    clean = restore_joined_schedule_rows(str(text or ""))
    return (
        STRUCTURED_SCHEDULE_WRITER_RULE_2313
        if _SCHEDULE_CONTEXT.search(clean) and len(_TIME_ATOM.findall(clean)) >= 4
        else ""
    )


# Complete explicit group rows; no date inference or arithmetic. The source
# itself remains immutable. Reject ambiguous duplicate groups / partial rows.
_GROUP_ROW_2366 = re.compile(r"(?<![\d.])([1-6]\.[12])\s*[:：]\s*")
_CLOCK_2366 = r"(?:[01]\d|2[0-3]):[0-5]\d|24:00"
_RANGE_2366 = re.compile(r"(?:" + _CLOCK_2366 + r")\s*[–—-]\s*(?:" + _CLOCK_2366 + r")")


def schedule_rows_2366(raw: str) -> tuple[tuple[str, str], ...]:
    text = restore_joined_schedule_rows(raw)
    if not _SCHEDULE_CONTEXT.search(text):
        return ()
    matches = list(_GROUP_ROW_2366.finditer(text))
    rows = []
    for i, match in enumerate(matches):
        end = matches[i+1].start() if i+1 < len(matches) else len(text)
        tail = text[match.end():end].strip()
        # Only accept an entire row containing ranges; no partial/guessed table.
        parts = [part.strip() for part in tail.split(',')]
        if not parts or not all(_RANGE_2366.fullmatch(part) for part in parts):
            return ()
        rows.append((match[1], tail))
    return tuple(rows) if len(rows) >= 2 and len({group for group, _ in rows}) == len(rows) else ()


def schedule_row_guidance_2366(raw: str) -> str:
    rows = schedule_rows_2366(raw)
    if not rows:
        return ""
    return ("ТОЧНІ РЯДКИ ОДНІЄЇ ТАБЛИЦІ SOURCE (не нові факти):\n"
            + "\n".join(f"{group}: {times}" for group, times in rows)
            + "\nНе переставляй проміжки між чергами, не виводь дату з часу обробки; використовуй лише прямо вказану у SOURCE дату. Не копіюй усі рядки, якщо це не вміщується; дій за правилами каналу та збережи посилання на першоджерело.\n")
