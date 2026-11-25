"""Source-verified punctuation-only repair before the complete existing QA.

Never complete unfinished claims, invent quote content, or repair ambiguous
parentheses. An opening Ukrainian guillemet may be closed ONLY if the exact
word sequence is quoted and closed in the ORIGINAL article source.
"""
from __future__ import annotations
import re
from typing import Any


def _field(row: Any, name: str) -> str:
    try:
        v = row[name]
    except (KeyError, TypeError, IndexError):
        v = getattr(row, name, "")
    return str(v or "")


def source_verified_guillemet_2356(article: Any, value: str) -> str:
    text = str(value or "")
    if (text.count("«") != 1 or text.count("»") != 0
            or len(text) < 130 or len(text) > 900):
        return text
    start = text.index("«")
    after = text[start+1:]
    # Source OWN words; do not infer where an entire quoted sentence ends.
    match = re.match(r"([\wА-Яа-яІіЇїЄєҐґ’' -]{3,65})", after)
    if not match:
        return text
    snippet = match.group(1).rstrip()
    # Prefer the longest punctuation-bounded source quote ending near the
    # opening in this candidate, rather than adding a guillemet at the end.
    original = _field(article,"raw_text") + "\n" + _field(article,"title")
    options = [m.group(1) for m in re.finditer(r"«([^«»\n]{3,65})»",original)
               if after.startswith(m.group(1))]
    if len(options) != 1:
        return text
    quoted = options[0]
    boundary = start+1+len(quoted)
    # Avoid inserting in the middle of a longer token or across free prose.
    if boundary < len(text) and (text[boundary].isalnum() or text[boundary] in "’'-"):
        return text
    return text[:boundary] + "»" + text[boundary:]

__all__=["source_verified_guillemet_2356"]
