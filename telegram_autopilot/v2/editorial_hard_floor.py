"""Operator P0 source-to-post hard checks (2.2.24).

No model call, channel setting mutation, or inferred second fact.
"""
from __future__ import annotations

import re
from typing import Any


def _v(row: Any, key: str) -> str:
    try:
        return str(row[key] or "")
    except (KeyError, IndexError, TypeError):
        return str(getattr(row, key, "") or "")


_ABBREVIATIONS = re.compile(r"(?iu)\b(?:м|с|вул|просп|ім|обл|р-н|ст|р|грн|тис|млн|п|т|д|ін|тощо)\.(?=\s|$)")
_SENTENCE = re.compile(r"(?s)([^.!?…]+[.!?…]+)(?=\s|$)")
_WORD = re.compile(r"[А-Яа-яІіЇїЄєҐґA-Za-z]{2,}")
_REPEAT_STOP = frozenset("про це також повідомили зазначили й та але що було стали може сьогодні вчора".split())


def facts(text: str) -> tuple[str, ...]:
    """Completed prose sentences, without headings/footer/URL/abbreviations.

    This conservative structural count is a FLOOR, not proof of entailment.
    For a real publication the independent fact-grounding gates remain required.
    """
    body = re.sub(r"https?://\S+|t\.me/\S+", " ", str(text or ""), flags=re.I)
    body = re.sub(r"(?m)^\s*(?:читати\s+у|джерело\s*[:：]|#\w+|[А-ЯІЇЄҐ A-Z]{3,}\s*\|\s*[А-ЯІЇЄҐ A-Z]{3,})[^\n]*$", "", body, flags=re.I)
    body = _ABBREVIATIONS.sub(" ", body)
    results = []
    for match in _SENTENCE.finditer(body):
        s = match.group(1).strip(" \n\t•-—🚧⚡️🕯")
        words = _WORD.findall(s)
        if len(words) >= 3 and not s.startswith(("#", "@")):
            results.append(s)
    return tuple(results)


def two_sentence_reason(article: Any, final_text: str | None = None) -> str:
    raw = _v(article, "raw_text")
    # Source headline can only complement the BODY when original raw_text is
    # itself absent; never manufacture support by duplicating title + raw_text.
    source = raw if raw.strip() else _v(article, "title")
    if len(facts(source)) < 2:
        return "EDITORIAL_MIN_TWO_SENTENCES: source"
    if final_text is not None and len(facts(final_text)) < 2:
        return "EDITORIAL_MIN_TWO_SENTENCES: final"
    return ""


_AIR_ALERT = re.compile(
    r"(?iu)\b(?:реактив\w*|мопед(?:и|ів|ами)?|"
    r"бандерол\w*|шахед\w*|бпла|дрон\w*|ппо|"
    r"ракет\w*|літак\w*)\b"
)
_AIR_ROUTE = re.compile(
    r"(?iu)\b(?:лет\w*|вилет\w*|полет\w*|курс\w*|"
    r"кружля\w*|крут\w*|напрям\w*|через|повз|над)\b"
)
_SETTLED = re.compile(r"(?iu)\b(?:загинул\w*|поранен\w*|пошкоджен\w*|зруйнован\w*|ліквідовано|підтвердили\s+наслідки)\b")
_TRAFFIC = re.compile(r"(?iu)\b(?:перекри\w*|обмеж\w*\s+рух\w*|об.?їзд|дорожн\w*\s+робот\w*|віднов\w*\s+рух\w*)\b")
_KIN = re.compile(r"(?iu)\b(?:одна\s+родина|однією\s+родиною|усі\s+(?:троє|три)\s+(?:однієї\s+)?родини)\b")


def fabricated_event_reason(article: Any, final_text: str) -> str:
    original = (_v(article, "raw_text") + " " + _v(article, "title")).casefold()
    outgoing = str(final_text or "").casefold()
    if _AIR_ALERT.search(original) and _AIR_ROUTE.search(original) and not _SETTLED.search(original):
        return "MONITORING_UNSETTLED_AERIAL_SOURCE"
    if _AIR_ALERT.search(original) and _AIR_ROUTE.search(original) and _TRAFFIC.search(outgoing) and not _TRAFFIC.search(original):
        return "FACT_UNSUPPORTED_TRAFFIC_CLOSURE"
    if _KIN.search(outgoing) and not _KIN.search(original):
        return "FACT_UNSUPPORTED_GROUP_KINSHIP"
    # A source describing a pair as family cannot extend it to 3 people.
    if re.search(r"\b(?:троє|трьох|три)\b", outgoing) and _KIN.search(outgoing) and not re.search(r"(?iu)\b(?:троє|трьох|три)\b.{0,70}\bродин", original):
        return "FACT_UNSUPPORTED_GROUP_KINSHIP"
    return ""
