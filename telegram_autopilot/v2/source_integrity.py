"""Conservative provenance gate for publisher pages that merge multiple stories.

A native page extractor may incorrectly treat related-story cards/teasers as
one article and their unrelated pictures as a valid story gallery. Fail closed
before asking AI to invent a coherent interpretation of unrelated stories.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

_STOP = frozenset(
    "about after again also been being better could does each from have into more "
    "other than that their them then there these this through time what when where "
    "which while with would were your our question getting you some only just "
    "most still article story media news read".split()
)
_WORD = re.compile(r"[a-z]{4,}|[а-яіїєґ]{4,}", re.I)
_SHORT_LINE = 145


def _value(row: Any, key: str) -> str:
    try:
        value = row[key]
    except (KeyError, TypeError, IndexError):
        value = getattr(row, key, "")
    return str(value or "").strip()


def _tokens(text: str) -> set[str]:
    return {token for token in _WORD.findall(text.casefold()) if token not in _STOP}


def multi_story_page_cards_reason(article: Any) -> str:
    """High-confidence page contamination; no model/provider heuristics.

    At least three alternating independent news headings + substantial teasers,
    with little overlap between the claimed URL article headline and extracted
    body, show that we collected recommendation cards, not its content.
    """
    url = _value(article, "canonical_source_url") or _value(article, "source_url")
    host = (urlsplit(url).hostname or "").lower()
    if not host or "t.me" in host or "telegram" in host:
        return ""
    title = _value(article, "title")
    raw = _value(article, "raw_text")
    if len(raw) < 320 or len(raw) > 7000:
        return ""
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if len(lines) < 6:
        return ""
    heads = []
    for i in range(len(lines)-1):
        # Teaser cards: standalone headline followed by an explanatory blurb,
        # repeated for DIFFERENT stories on the same publisher page.
        heading, blurb = lines[i], lines[i+1]
        if 25 <= len(heading) <= _SHORT_LINE and len(blurb) >= 100:
            if len(_tokens(heading)) >= 4 and len(_tokens(blurb)) >= 12:
                heads.append(heading)
    if len(heads) < 3:
        return ""
    # Avoid rejecting long coherent articles with multiple subheadings.
    distinct = {frozenset(_tokens(x)) for x in heads}
    if len(distinct) < 3:
        return ""
    headline = _tokens(title)
    if len(headline) < 3:
        return ""
    title_overlap = len(headline & _tokens(raw)) / len(headline)
    if title_overlap > 0.40:
        return ""
    # The page's named story is absent, but multiple other stories dominate.
    return (
        "EDITORIAL_MULTI_STORY_PAGE_CARDS: "
        f"{len(heads)} unrelated headline/teaser pairs on single URL; "
        f"claimed title overlap={title_overlap:.2f}, not a verified article"
    )
