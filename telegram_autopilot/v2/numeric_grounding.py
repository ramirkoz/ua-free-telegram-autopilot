"""Number grounding: every number in a draft must be supported by the source.

The former check compared raw tokens, so a correct draft was rejected when it
merely wrote a source number properly:

* source ``з 10.00до 11.00`` / ``з 10-00``  -> draft ``10:00`` ("invented")
* source ``20.11.2026Про`` (glued to a word) -> draft ``2026`` ("invented")
* source ``+380672738096Не`` / ``+38 099 009 35 90`` -> any phone ("invented")
* source ``8,3 млн``                         -> draft ``8,3`` vs ``83``

Both sides are now reduced to canonical values (clock time, date, phone,
decimal, integer). The check itself is unchanged in strictness: a value that
the source does not contain is still reported, including a malformed time
such as ``21:3041`` and any number the model made up.
"""
from __future__ import annotations

import re

from .numeric_schedule_2313 import restore_joined_schedule_rows

_URL = re.compile(r"https?://\S+|t\.me/\S+", re.I)
_LETTER = "A-Za-zА-Яа-яІіЇїЄєҐґ"
_DIGIT_THEN_LETTER = re.compile(rf"(?<=\d)(?=[{_LETTER}])")
_LETTER_THEN_DIGIT = re.compile(rf"(?<=[{_LETTER}])(?=\d)")
_PHONE = re.compile(r"(?<![\w.])\+?\d[\d  ()\-]{8,}\d(?!\w)")
_DATE = re.compile(r"(?<![\d.])(\d{1,2})\.(\d{1,2})\.(\d{4}|\d{2})(?![\d.])")
_CLOCK = re.compile(r"(?<![\d:.,])([01]?\d|2[0-4])([:.\-])([0-5]\d)(?![\d:])")
_COLON = re.compile(r"(?<!\d)\d+(?::\d+)+(?!\d)")
_THOUSANDS = re.compile(r"(?<![\d.,])\d{1,3}(?:[  ]\d{3})+(?![\d.,])")
_DECIMAL = re.compile(r"(?<![\d.,])\d+[.,]\d+(?![\d.,])")
_INT = re.compile(r"(?<![\d.,:])\d+(?![\d.,:])")


def _prepare(text: str) -> str:
    clean = _URL.sub(" ", str(text or ""))
    clean = restore_joined_schedule_rows(clean)
    # Telegram extraction glues the end of one sentence to the next word.
    clean = _DIGIT_THEN_LETTER.sub(" ", clean)
    return _LETTER_THEN_DIGIT.sub(" ", clean)


def _int(value: str) -> str:
    return str(int(value))


def _atoms(text: str, *, generous: bool) -> set[str]:
    """Canonical numeric values. ``generous`` adds the readings a source supports."""
    clean = _prepare(text)
    out: set[str] = set()

    def take(pattern, handler):
        nonlocal clean
        for match in pattern.finditer(clean):
            handler(match)
        clean = pattern.sub(" ", clean)

    def phone(match):
        digits = re.sub(r"\D", "", match.group())
        if len(digits) >= 9:
            out.add("tel:" + digits[-9:])
        else:
            out.add(_int(digits))
    take(_PHONE, phone)

    def date(match):
        day, month, year = match.group(1), match.group(2), match.group(3)
        year = year if len(year) == 4 else "20" + year
        out.add(f"{int(day)}.{int(month)}.{year}")
        if generous:   # "20.11.2026" supports "20 листопада 2026 року"
            out.update({_int(day), year, f"{int(day)}.{int(month)}"})
    take(_DATE, date)

    def clock(match):
        hour, sep, minute = match.group(1), match.group(2), match.group(3)
        as_time = f"{int(hour)}:{minute}"
        as_decimal = f"{int(hour)}.{minute}".rstrip("0").rstrip(".") if sep != ":" else ""
        if sep == ":":
            out.add(as_time)
        elif generous:   # "10.00" / "10-00" may be a time or a decimal/range
            out.add(as_time)
            if sep == ".":
                out.add(f"{int(hour)}.{minute}")
                out.add(as_decimal or _int(hour))
            else:
                out.update({_int(hour), _int(minute)})
        elif sep == ".":
            out.add(f"{int(hour)}.{minute}")
        else:
            out.update({_int(hour), _int(minute)})
    take(_CLOCK, clock)

    take(_COLON, lambda m: out.add(m.group()))          # malformed times stay as written
    take(_THOUSANDS, lambda m: out.add(re.sub(r"\D", "", m.group())))

    def decimal(match):
        value = match.group().replace(",", ".")
        whole, frac = value.split(".", 1)
        out.add(f"{int(whole)}.{frac}")
        if generous:
            out.add(f"{int(whole)}.{frac}".rstrip("0").rstrip("."))
    take(_DECIMAL, decimal)

    take(_INT, lambda m: out.add(_int(m.group())))
    return out


def supported_numbers(source: str) -> set[str]:
    return _atoms(source, generous=True)


def claimed_numbers(text: str) -> set[str]:
    return _atoms(text, generous=False)


def unsupported_numbers(source: str, text: str) -> list[str]:
    """Numbers stated in ``text`` that ``source`` does not contain."""
    support = supported_numbers(source)
    missing = []
    for atom in sorted(claimed_numbers(text)):
        if atom in support:
            continue
        # "8.30" in a draft is supported by a source "8.3" and vice versa.
        if "." in atom and atom.rstrip("0").rstrip(".") in support:
            continue
        missing.append(atom.replace("tel:", "…"))
    return missing
