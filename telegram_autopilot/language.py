from __future__ import annotations

import re

_EN_WORDS = {"the","and","that","this","with","from","for","into","after","before","over","under","said","says","will","has","have","was","were","are","is","to","of","in","on","as","at","by","its","their"}
_UA_LETTERS = set("іїєґІЇЄҐ")
_CYRILLIC = re.compile(r"[А-Яа-яІіЇїЄєҐґ]")
_LATIN = re.compile(r"[A-Za-z]")
_WORD = re.compile(r"[A-Za-z']+")

# Small editorial glossary of mistakes actually observed in production. This is not a
# universal translator: it exists to stop known calques from escaping into autopublish.
_TERMINOLOGY_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bелектронно[- ]лумова\s+трубка\b", re.I), "електронно-променева трубка"),
    (re.compile(r"\bелектронно[- ]лумової\s+трубки\b", re.I), "електронно-променевої трубки"),
    (re.compile(r"\bелектронно[- ]лумову\s+трубку\b", re.I), "електронно-променеву трубку"),
    (re.compile(r"\bкатодно[- ]променева\s+трубка\b", re.I), "електронно-променева трубка"),
    (re.compile(r"\bкатодно[- ]променевої\s+трубки\b", re.I), "електронно-променевої трубки"),
    (re.compile(r"\bтемний\s+ринок\b", re.I), "даркнет-майданчик"),
    (re.compile(r"\bтемного\s+ринку\b", re.I), "даркнет-майданчика"),
    (re.compile(r"\bтемному\s+ринку\b", re.I), "даркнет-майданчику"),
    (re.compile(r"\bтемним\s+ринком\b", re.I), "даркнет-майданчиком"),
    (re.compile(r"\bтемна\s+мережа\b", re.I), "даркнет"),
    (re.compile(r"\bтемної\s+мережі\b", re.I), "даркнету"),
)

_BAD_TERMS = (
    "електронно-лумов", "електронно лумов", "катодно-променев", "катодно променев",
    "темний ринок", "темного ринку", "темному ринку",
)
_STRONG_CAPTION_CLAIMS = (
    "підтверджує", "доводить", "засвідчує", "демонструє, що", "свідчить про те, що",
    "proves", "confirms that", "shows that",
)


def looks_english(text: str) -> bool:
    sample = (text or "")[:12000]
    latin = len(_LATIN.findall(sample))
    cyr = len(_CYRILLIC.findall(sample))
    words = [w.casefold() for w in _WORD.findall(sample)]
    common = sum(1 for w in words if w in _EN_WORDS)
    return latin >= 120 and latin > cyr * 4 and common >= 4


def looks_ukrainian(text: str) -> bool:
    sample = (text or "")[:8000]
    cyr = len(_CYRILLIC.findall(sample))
    latin = len(_LATIN.findall(sample))
    ua = sum(ch in _UA_LETTERS for ch in sample)
    return cyr >= 80 and cyr > latin * 2 and ua >= 2


def normalize_ukrainian_terminology(text: str) -> str:
    value = str(text or "")
    for pattern, replacement in _TERMINOLOGY_REPLACEMENTS:
        value = pattern.sub(replacement, value)
    value = re.sub(r"\bCRT[- ]телевізор", "ЕПТ-телевізор", value, flags=re.I)
    return value


def terminology_issues(text: str) -> tuple[str, ...]:
    low = str(text or "").casefold()
    return tuple(term for term in _BAD_TERMS if term in low)


def sanitize_media_caption(candidate: str, source_caption: str = "", source_alt: str = "") -> str:
    """Keep captions conservative. A model may translate source wording, not invent a visual claim."""
    clean = " ".join(str(candidate or "").split()).strip()
    source = " ".join((str(source_caption or "") + " " + str(source_alt or "")).split()).strip()
    if not clean or not source:
        return ""
    low = clean.casefold()
    source_low = source.casefold()
    if any(claim in low and claim not in source_low for claim in _STRONG_CAPTION_CLAIMS):
        return ""
    # Numbers are especially dangerous in hallucinated captions. Keep only numbers that
    # also exist in the source caption/alt metadata.
    source_numbers = set(re.findall(r"\d+(?:[.,]\d+)?", source))
    candidate_numbers = set(re.findall(r"\d+(?:[.,]\d+)?", clean))
    if not candidate_numbers.issubset(source_numbers):
        return ""
    return normalize_ukrainian_terminology(clean)[:1000]
