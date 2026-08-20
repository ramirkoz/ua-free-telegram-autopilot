from __future__ import annotations

import re
from dataclasses import dataclass
from sqlite3 import Row


_SENTENCE_RE = re.compile(r"(?<=[.!?…])\s+")
_LATIN_ENTITY_RE = re.compile(r"\b(?:[A-Z][A-Za-z0-9.+_-]{2,}|[A-Za-z]+\d[A-Za-z0-9.+_/-]*)\b")
_UNIT_RE = re.compile(
    r"\b\d+(?:[.,]\d+)?\s?(?:%|GHz|MHz|kHz|GB|TB|MB|KB|W|kW|MW|GW|V|mV|km|m|cm|mm|kg|g|°C|fps|Hz|nm)\b",
    re.IGNORECASE,
)
_ATTRIBUTION = (
    "said", "says", "according to", "announced", "reported", "told", "claims", "claimed",
    "expects", "plans", "planned", "will", "may", "might", "could", "study", "researchers",
    "company", "agency", "university", "paper", "report",
)


@dataclass(frozen=True, slots=True)
class EvidencePack:
    text: str
    source_length: int
    selected_sentences: int
    truncated: bool


def _row_text(article: Row, key: str) -> str:
    try:
        return str(article[key] or "")
    except (KeyError, IndexError, TypeError):
        return ""


def _sentences(raw: str) -> list[str]:
    compact = " ".join(str(raw or "").split())
    if not compact:
        return []
    return [part.strip() for part in _SENTENCE_RE.split(compact) if part.strip()]


def _score(sentence: str, index: int) -> int:
    low = sentence.casefold()
    score = max(0, 7 - index) if index < 7 else 0
    if any(ch.isdigit() for ch in sentence):
        score += 7
    score += min(8, len(_LATIN_ENTITY_RE.findall(sentence)) * 2)
    if _UNIT_RE.search(sentence):
        score += 5
    if any(term in low for term in _ATTRIBUTION):
        score += 4
    if '"' in sentence or "“" in sentence or "”" in sentence:
        score += 2
    if any(term in low for term in ("first", "largest", "biggest", "fastest", "record", "most powerful", "world's first")):
        score += 5
    return score


def build_evidence_pack(article: Row, *, char_budget: int) -> EvidencePack:
    """Build a bounded, deterministic evidence pack without an extra AI call.

    The old compactor mostly kept the beginning of a long article. This pack
    keeps the lead but also reserves room for fact-bearing sentences containing
    numbers, entities, units, attribution and high-risk claims from later in the
    source. Original sentence order is preserved in the final pack.
    """
    budget = max(600, int(char_budget))
    title = " ".join(_row_text(article, "title").split())
    published = " ".join(_row_text(article, "source_published_at").split()) or "unknown"
    raw = " ".join(_row_text(article, "raw_text").split())
    sentences = _sentences(raw)

    title_limit = min(700, max(120, budget // 4))
    prefix = f"TITLE: {title[:title_limit]}\nSOURCE DATE: {published[:120]}\nSELECTED SOURCE PASSAGES:\n"
    available = max(300, budget - len(prefix))
    if len(raw) <= available:
        body = raw
        return EvidencePack((prefix + body).strip(), len(raw), len(sentences), False)

    chosen: set[int] = set()

    def current_len(indices: set[int]) -> int:
        return len(" ".join(sentences[i] for i in sorted(indices)))

    for idx in range(min(2, len(sentences))):
        candidate = set(chosen)
        candidate.add(idx)
        if current_len(candidate) <= available:
            chosen = candidate

    ranked = sorted(range(len(sentences)), key=lambda i: (-_score(sentences[i], i), i))
    for idx in ranked:
        if idx in chosen:
            continue
        candidate = set(chosen)
        candidate.add(idx)
        if current_len(candidate) <= available:
            chosen = candidate

    ordered = [sentences[i] for i in sorted(chosen)]
    body = " ".join(ordered).strip()
    if not body and raw:
        cut = raw[:available].rstrip()
        boundary = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "), cut.rfind("… "))
        body = cut[: boundary + 1].strip() if boundary >= 120 else cut

    text = (prefix + body).strip()
    return EvidencePack(text[:budget].rstrip(), len(raw), len(ordered), True)
