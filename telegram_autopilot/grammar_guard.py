from __future__ import annotations

import re

from .ukrainian_quality import has_language_quality_risk

_WORD_RE = re.compile(r"[A-Za-zА-Яа-яІіЇїЄєҐґ0-9’'/-]+")
_NUMBER_RE = re.compile(r"(?<![A-Za-zА-Яа-яІіЇїЄєҐґ0-9])(?:\d{1,3}(?:[ \u00a0\u202f,]\d{3})+|\d+)(?:[.,]\d+)?(?:\s?%)?")
_LATIN_RE = re.compile(r"\b(?:[A-Z][A-Za-z0-9._+-]{2,}|[A-Z]{2,}[A-Z0-9._+-]*|[A-Za-z]+\d+[A-Za-z0-9._+-]*)\b")
_RELATIVE = {"який", "яка", "яке", "які", "котрий", "котра", "котре", "котрі"}
_STOP = {"але", "або", "без", "був", "була", "були", "було", "буде", "від", "для", "до", "із", "на", "не", "після", "по", "про", "та", "також", "у", "це", "що"}

_GRAMMAR_RISK_PATTERNS = (
    re.compile(r"\bрозплавен\w*\s+сол", re.I),
    re.compile(r"\bпростаю\w*\b", re.I),
    re.compile(r"\bскачк\w*\b", re.I),
    re.compile(r"\bзадоволення\s+(?:стрибк|скачк)\w*", re.I),
    re.compile(r"(?<![-\w])\d+(?:[.,]\d+)?\s+(?:мегават|гігават)\b", re.I),
    re.compile(r"\bза\s+лічильником\b", re.I),
)


def _sentences(value: str) -> list[str]:
    compact = " ".join(str(value or "").split())
    return [part.strip() for part in re.split(r"(?<=[.!?…])\s+", compact) if part.strip()]


def needs_grammar_polish(value: str) -> bool:
    """Flag syntax where Ukrainian agreement errors are most likely.

    This is deliberately conservative. The proofread is optional and never
    blocks publication if no second cloud provider is available.
    """
    text = str(value or "")
    sentences = _sentences(text)
    if not sentences:
        return False
    if any(pattern.search(text) for pattern in _GRAMMAR_RISK_PATTERNS):
        return True
    if has_language_quality_risk(text):
        return True
    # Longer finished posts deserve one bounded copy-edit pass.  It is optional
    # and fact-checked again, so this improves human readability without becoming
    # a publication blocker when providers are unavailable.
    if len(text) >= 500 and len(sentences) >= 4:
        return True
    for sentence in sentences:
        words = [w.casefold() for w in _WORD_RE.findall(sentence)]
        if len(words) >= 24:
            return True
        if len(words) >= 18 and sentence.count(",") >= 2:
            return True
        if len(words) >= 15 and any(word in _RELATIVE for word in words):
            return True
    return False


def _norm_number(raw: str) -> str:
    item = str(raw or "").strip().rstrip("%").replace("\u00a0", " ").replace("\u202f", " ")
    item = re.sub(r"\s+", " ", item).strip().replace(" ", "")
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+", item):
        return item.replace(",", "")
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", item):
        return item.replace(".", "")
    if "," in item and "." in item:
        if item.rfind(",") > item.rfind("."):
            return item.replace(".", "").replace(",", ".")
        return item.replace(",", "")
    if "," in item:
        return item.replace(",", ".")
    return item


def _norm_numbers(value: str) -> set[str]:
    return {_norm_number(match.group(0)) for match in _NUMBER_RE.finditer(str(value or ""))}


def _anchors(value: str) -> set[str]:
    return {x.casefold() for x in _LATIN_RE.findall(str(value or ""))}


def _content_tokens(value: str) -> set[str]:
    result = set()
    for raw in _WORD_RE.findall(str(value or "")):
        low = raw.casefold().strip("-'_/.")
        if len(low) >= 4 and low not in _STOP:
            result.add(low)
    return result


def preserves_content(original: str, polished: str) -> bool:
    """Reject a 'grammar correction' that actually rewrites the story."""
    a = str(original or "").strip()
    b = str(polished or "").strip()
    if not a or not b:
        return False
    ratio = len(b) / max(1, len(a))
    if ratio < 0.72 or ratio > 1.22:
        return False
    if _norm_numbers(a) != _norm_numbers(b):
        return False
    if _anchors(a) != _anchors(b):
        return False
    a_tokens = _content_tokens(a)
    b_tokens = _content_tokens(b)
    if not a_tokens:
        return True
    return len(a_tokens & b_tokens) / len(a_tokens) >= 0.67


def preserves_human_copyedit(original: str, polished: str) -> bool:
    """Allow safe editorial compression while rejecting semantic expansion.

    Unlike the stricter grammar-only guard, a human-style pass may remove
    repetitive or secondary details. It may not introduce new numbers or named
    Latin entities, and the resulting text still needs substantial lexical
    grounding in the original candidate.
    """
    a = str(original or "").strip()
    b = str(polished or "").strip()
    if not a or not b:
        return False
    ratio = len(b) / max(1, len(a))
    if ratio < 0.45 or ratio > 1.12:
        return False
    if not _norm_numbers(b).issubset(_norm_numbers(a)):
        return False
    if not _anchors(b).issubset(_anchors(a)):
        return False
    a_tokens = _content_tokens(a)
    b_tokens = _content_tokens(b)
    if not b_tokens:
        return False
    # Most words in the polished version must already belong to the accepted
    # candidate. The final article-level Fact Guard still runs afterwards.
    return len(a_tokens & b_tokens) / len(b_tokens) >= 0.64
