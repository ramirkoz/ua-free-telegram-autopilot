"""Operator 2026-10-23: no one-sentence filler, invented relations or event-type flips.

Conservative source-owned deterministic hard stops. No LLM/network calls.
"""
from __future__ import annotations

import re
from typing import Any

_WORDS = re.compile(r"(?iu)\b[а-яіїєґa-z]{3,}\b")
_SPLIT = re.compile(r"(?<=[.!?…])(?:\s+|(?=[А-ЯІЇЄҐA-Z]))")
_URL = re.compile(r"https?://\S+", re.I)
_META = re.compile(r"(?iu)^\s*(?:джерело\s*:|читати\s+у\s+[«\"']|https?://|@[\w.]+)\b")
_TRAFFIC_INVENTED = re.compile(
    r"(?iu)(?:\b(?:перекри\w*|перекрит\w*|обмежил\w*\s+рух|"
    r"проїзд\s+(?:закрит\w*|перекрит\w*)|"
    r"об.?їзд\w*|дорожн\w*\s+робот\w*|"
    r"рух\s+віднов\w*)\b)"
)
_JET = re.compile(r"(?iu)\b(?:реактивн\w*\s+літак\w*|літак\w*)\b")
_REACTIVE = re.compile(r"(?iu)\bреактив\w*\b")
_FAMILY_ALL = re.compile(
    r"(?iu)(?:\bце\s+була\s+одна\s+родина\b|"
    r"\b(?:усі|всі|втрьох|троє)\b.{0,65}\b(?:родин\w*|сім.?я\w*)\b|"
    r"\b(?:однієї|одної|однієї)\s+родини\b)"
)
_FAMILY_ALL_SOURCE = re.compile(
    r"(?iu)(?:\b(?:усі|всі)\s+троє\b.{0,70}\b(?:родин|сім)|"
    r"\bтроє\s+(?:член\w*\s+)?(?:однієї\s+)?(?:родин|сім)|"
    r"\b(?:усі|всі)\s+загибл\w*\b.{0,70}\b(?:родин|сім))"
)


def _v(row: Any, key: str) -> str:
    try:
        return str(row[key] or "")
    except (KeyError, IndexError, TypeError):
        return str(getattr(row, key, "") or "")


def substantive_sentences(value: str) -> tuple[str, ...]:
    """Only complete body sentences. Header/footer, URLs, URLs' dots excluded.

    Independent sentences must have a verb or at least substantive factual
    structure; exact repeated paraphrases do not inflate the count.
    """
    cleaned = _URL.sub("", str(value or ""))
    candidates = []
    for line in cleaned.splitlines():
        if _META.search(line):
            continue
        line = re.sub(r"(?iu)^\s*(?:[-•*]|\d+[).])\s*", "", line).strip()
        candidates.extend(_SPLIT.split(line))
    seen: list[set[str]] = []
    kept = []
    for candidate in candidates:
        sentence = candidate.strip(" \t\r\n\"'«»()[]—–•🚨🔴⚠️")
        if not re.search(r"[.!?…][»”\"')\]]*$", sentence):
            continue
        words = _WORDS.findall(sentence.casefold())
        # Pure source reference, heading, a time/date or noisy tag isn't news.
        substantive = {w for w in words if w not in {
            "читати", "джерело", "підписатися", "підписуйтесь",
            "сьогодні", "завтра", "новини", "оновлення", "увага",
        }}
        if len(substantive) < 4 or len(sentence) < 25:
            continue
        # Identical sentence or near-copy of a single claim does not count twice.
        if any(len(substantive & old) / max(1, min(len(substantive),len(old))) >= .86
               for old in seen):
            continue
        kept.append(sentence)
        seen.append(substantive)
    return tuple(kept)


def minimum_sentence_reason(article: Any, final_text: str | None = None) -> str:
    source = _v(article, "raw_text") or _v(article, "title")
    if len(substantive_sentences(source)) < 2:
        return "EDITORIAL_MIN_TWO_SENTENCES_SOURCE"
    if final_text is not None and len(substantive_sentences(final_text)) < 2:
        return "EDITORIAL_MIN_TWO_SENTENCES_FINAL"
    return ""


def unsupported_event_claims(article: Any, output: str) -> tuple[str, ...]:
    source = (_v(article,"title") + " " + _v(article,"raw_text")).casefold()
    final = str(output or "").casefold()
    issues = []
    # Operator #76105: airborne munition passing bridges -> invented road closure.
    if _TRAFFIC_INVENTED.search(final) and not _TRAFFIC_INVENTED.search(source):
        issues.append("EDITORIAL_UNSUPPORTED_TRAFFIC_EVENT")
    # Operator #76065: ambiguous "реактив" -> asserted jet aircraft.
    if _JET.search(final) and _REACTIVE.search(source) and not _JET.search(source):
        issues.append("EDITORIAL_UNSUPPORTED_AIRCRAFT_IDENTITY")
    # Operator #75930: two family members and an unrelated third fatality.
    if _FAMILY_ALL.search(final) and not _FAMILY_ALL_SOURCE.search(source):
        issues.append("EDITORIAL_UNSUPPORTED_ALL_VICTIMS_FAMILY")
    return tuple(issues)
