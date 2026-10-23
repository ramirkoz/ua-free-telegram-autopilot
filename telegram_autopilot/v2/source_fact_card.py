"""2.2.27: compact, original-source-owned newsroom fact card.

This is a *provenance-indexed briefing*, not another AI summary or an
entailment verdict. Every factual snippet is copied from the original source.
ANGLE, channel policy, model output and learning memory never enter the card.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .evidence_ledger import extract_source_evidence

_PERCENT = re.compile(r"(?iu)(?<!\w)\d+(?:[.,]\d+)?\s*%")
_AMOUNT = re.compile(r"(?iu)(?<!\w)(?:[$€£₴]\s*\d[\d.,]*|\d[\d.,]*\s*(?:usd|eur|грн|долар\w*|млн|млрд))\b")
_ATTRIBUTION = re.compile(
    r"(?iu)\b(?:according to|reported|study|researchers|survey|said|"
    r"за даними|дослідженн\w*|опитуванн\w*|повідомил\w*|заявил\w*|"
    r"за словами|зазначил\w*|планує|може|ймовірно)\b"
)
_PRACTICAL = re.compile(
    r"(?iu)\b(?:дедлайн|реєстрац\w*|адрес\w*|вулиц\w*|проспект\w*|"
    r"записат\w*|отримат\w*|звернут\w*|заявк\w*|дата|"
    r"до\s+\d{1,2}\s+(?:січ|лют|бер|кві|тра|чер|лип|сер|вер|жов|лис|гру))"
)


def _v(article: Any, key: str) -> str:
    try:
        value = article[key]
    except (KeyError, IndexError, TypeError):
        value = getattr(article, key, "")
    return str(value or "")


def _compact(text: str) -> str:
    return " ".join(str(text or "").split()).strip()


@dataclass(frozen=True)
class SourceFactCard:
    text: str
    source_id: str
    source_title: str
    direct_quotes: tuple[str, ...]
    statistic_contexts: tuple[str, ...]
    truncated: bool

    def source_spans_valid(self, original: str) -> bool:
        return all(quote in str(original or "") for quote in self.direct_quotes)


def build_source_fact_card(article: Any, *, char_budget: int = 1900) -> SourceFactCard:
    """Bounded deterministic source spans, with full statistic *contexts*.

    Headline is only a source headline, not proof of extra participants or
    relationships. All bullets are literal spans, including qualifiers.
    """
    budget = max(500, min(3600, int(char_budget)))
    raw = _v(article, "raw_text")
    source_title = _compact(_v(article, "title"))[:260]
    source_id = (_v(article, "canonical_source_url")
                 or _v(article, "source_url") or f"article:{_v(article, 'id') or 'unknown'}")
    ledger = extract_source_evidence(raw, source_id=source_id)
    entries = [entry.quote.strip() for entry in ledger.entries if entry.quote.strip()]
    # Pin the opening source facts; other sections can be important but must
    # not displace the event that the reader needs to understand.
    selected = list(range(min(2, len(entries))))
    statistic_indices = [i for i, quote in enumerate(entries) if _PERCENT.search(quote) or _AMOUNT.search(quote)]
    attributed_indices = [i for i, quote in enumerate(entries) if _ATTRIBUTION.search(quote)]
    practical_indices = [i for i, quote in enumerate(entries) if _PRACTICAL.search(quote)]
    order = selected + statistic_indices + attributed_indices + practical_indices
    chosen: list[int] = []
    for idx in order:
        if idx not in chosen:
            chosen.append(idx)
    for idx in range(len(entries)):
        if idx not in chosen:
            chosen.append(idx)

    prefix = (
        "КАРТКА ФАКТІВ ІЗ ПЕРШОДЖЕРЕЛА (цитати джерела, НЕ готовий пост):\n"
        f"SOURCE TITLE: {source_title}\n"
        f"SOURCE ID: {source_id[:190]}\n"
        "ВИКОРИСТАННЯ: установи головну дію/учасників із SOURCE. "
        "Не вигадуй ролей; проценти не перетворюй на частоту дій окремої людини; "
        "зберігай базу порівняння, період та уточнення. Якщо джерело не "
        "підтверджує зв'язку, не пиши його. ANGLE не є доказом.\n"
    )
    lines: list[str] = []
    kept: list[str] = []
    contexts: list[str] = []
    size = len(prefix)
    for idx in chosen:
        quote = entries[idx]
        if len(kept) >= 7:
            break
        # Long unpunctuated source blobs are abbreviated explicitly; don't
        # present a chopped sentence as a complete proposition.
        clipped = quote if len(quote) <= 460 else quote[:457].rstrip() + "… [уривок]"
        kind = "ЦИФРА В КОНТЕКСТІ" if idx in statistic_indices else (
            "АТРИБУЦІЯ/УМОВНІСТЬ" if idx in attributed_indices else (
                "ПРАКТИЧНІ УМОВИ" if idx in practical_indices else "ФАКТ ДЖЕРЕЛА"
            )
        )
        line = f"- [{kind}, фрагмент {idx + 1}] {clipped}"
        if size + len(line) + 1 > budget:
            continue
        lines.append(line)
        kept.append(quote)
        if idx in statistic_indices:
            contexts.append(quote)
        size += len(line) + 1
    body = prefix + "\n".join(lines)
    return SourceFactCard(
        text=body[:budget],
        source_id=source_id,
        source_title=source_title,
        direct_quotes=tuple(kept),
        statistic_contexts=tuple(contexts),
        truncated=(len(kept) < len(entries)),
    )
