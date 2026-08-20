from __future__ import annotations

import re

_EN_WORDS = {"the","and","that","this","with","from","for","into","after","before","over","under","said","says","will","has","have","was","were","are","is","to","of","in","on","as","at","by","its","their"}
_UA_LETTERS = set("іїєґІЇЄҐ")
_CYRILLIC = re.compile(r"[А-Яа-яІіЇїЄєҐґ]")
_LATIN = re.compile(r"[A-Za-z]")
_WORD = re.compile(r"[A-Za-zА-Яа-яІіЇїЄєҐґ’\'-]+")
_UA_COMMON = {
    "і","й","та","але","що","це","для","через","після","від","із","зі","який","яка","яке","які",
    "може","можуть","вже","ще","також","його","її","їх","під час","щоб","коли","де","тому","проте",
}
_UA_WORD_RE = re.compile(r"[А-Яа-яІіЇїЄєҐґ’\'-]+")
_LATIN_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9._+/-]*")

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
    """Recognize Ukrainian prose without punishing technical Latin names.

    The old character-ratio rule (Cyrillic > Latin * 2) rejected perfectly normal
    Ukrainian tech posts containing product/model/company names.  Work at word level
    instead: require a real Ukrainian sentence base and reject English function-word
    prose, while allowing many Latin entities such as Pixel, NVIDIA, OAuth or GPU.
    """
    sample = (text or "")[:8000]
    cyr_chars = len(_CYRILLIC.findall(sample))
    ua_specific = sum(ch in _UA_LETTERS for ch in sample)
    cyr_words = _UA_WORD_RE.findall(sample)
    latin_words = _LATIN_WORD_RE.findall(sample)
    low_cyr = [w.casefold().strip("’'-") for w in cyr_words]
    low_latin = [w.casefold().strip("'-") for w in latin_words]
    ua_hits = sum(1 for w in low_cyr if w in _UA_COMMON)
    en_hits = sum(1 for w in low_latin if w in _EN_WORDS)

    if cyr_chars < 45 or len(cyr_words) < 8:
        return False
    if ua_specific < 1 and ua_hits < 2:
        return False
    # A few English product words are fine; English grammatical prose is not.
    if en_hits >= max(5, len(cyr_words) // 3):
        return False
    if len(cyr_words) >= 12 and (ua_hits >= 2 or ua_specific >= 2):
        return True
    latin_chars = len(_LATIN.findall(sample))
    return cyr_chars >= max(45, int(latin_chars * 0.55)) and (ua_hits >= 2 or ua_specific >= 2)


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
