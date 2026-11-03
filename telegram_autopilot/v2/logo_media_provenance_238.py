"""2.3.8: final, source-grounded media choice for single-logo identity stories.

Creative Bloq 2026-11-02 #88700 and 2026-11-03 #89671 each delivered two
images although the news is about one logo. A common site-wide creative can be
an additional HTML image on both pages. Refuse unproven secondary images at the
last publication boundary. Do NOT collapse genuine article galleries elsewhere.
"""
from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit
from typing import Any

_SINGLE_IDENTITY_TOPIC = re.compile(
    r"\b(?:logo|logotype|wordmark|brandmark|rebrand(?:ing)?|identity)\b|"
    r"\b(?:логотип(?:у|ом|и)?|ребрендинг|айдентик[а-яіїєґ]*)\b", re.IGNORECASE
)
_WORD = re.compile(r"[a-zа-яіїєґ0-9]{3,}", re.IGNORECASE)
_GENERIC = {
    "logo", "logotype", "wordmark", "brandmark", "rebrand", "rebranding", "identity",
    "design", "designer", "graphic", "visual", "branding", "image", "photo", "photos",
    "news", "creative", "internet", "clever", "since", "2026", "2008", "the", "this",
    "that", "with", "from", "have", "been", "about", "again", "star", "real",
    "new", "back", "return", "returning", "site", "publisher", "social", "media",
    "логотип", "логотипу", "логотипом", "логотипи", "дизайн", "айдентика",
}
_BAD_CONTEXT = (
    "sponsored", "sponsor", "advert", "ad-slot", "ad_unit", "promoted",
    "related", "recommended", "trending", "read-next", "newsletter",
    "site-wide", "sitewide", "house-ad", "house_ad", "navigation", "site-header",
)


def _tokens(value: str) -> set[str]:
    return {x for x in _WORD.findall(unquote(str(value or "")).casefold())
            if x not in _GENERIC and len(x) >= 3}


def _bound_media_score(item: Any, *, title: str, raw_text: str) -> int:
    """Score only source image metadata, never model-generated final text."""
    try:
        asset_path = urlsplit(str(getattr(item, "url", "") or "")).path.rsplit("/", 1)[-1]
    except ValueError:
        asset_path = ""
    own = _tokens(" ".join((str(getattr(item, "alt", "") or ""),
                            str(getattr(item, "caption", "") or ""), asset_path)))
    title_words = _tokens(title)
    lead_words = _tokens(raw_text[:2400])
    title_hits = len(own & title_words)
    lead_hits = len(own & lead_words)
    score = title_hits * 9 + lead_hits * 3
    if title_hits and lead_hits:
        score += 5
    if bool(getattr(item, "schema_verified", False)):
        score += 4
    elif bool(getattr(item, "page_declared", False)):
        score += 3
    if str(getattr(item, "context", "")) == "open_graph_hint":
        score -= 4
    return score


def choose_identity_story_media_238(
    candidates: list[Any], *, title: str, raw_text: str, source_kind: str = "",
) -> tuple[list[Any], int]:
    """Return candidates and the number dropped for lack of story provenance.

    Only web editorial news whose HEADLINE is about a logo/brand mark is limited.
    A true, schema-verified multi-image story gallery remains intact. Never edit
    Telegram originals, non-identity stories or video identity.
    """
    if source_kind == "telegram" or not _SINGLE_IDENTITY_TOPIC.search(str(title or "")):
        return candidates, 0
    if len([c for c in candidates if getattr(c, "kind", "") == "image"]) <= 1:
        return candidates, 0

    images: list[tuple[Any, int, int]] = []
    for idx, item in enumerate(candidates):
        if getattr(item, "kind", "") != "image":
            continue
        context = str(getattr(item, "context", "") or "").casefold()
        if any(word in context for word in _BAD_CONTEXT):
            continue
        images.append((item, _bound_media_score(item, title=title, raw_text=raw_text), idx))

    if not images:
        return [], len(candidates)

    # Explicit schema-verified source gallery is credible; CSS `gallery=True`
    # alone is not, since publishers put recommendation/ad rails in galleries.
    if (len(images) >= 2 and all(getattr(item, "gallery", False) and
                                 getattr(item, "schema_verified", False)
                                 for item, _, _ in images)):
        permitted = {id(item) for item, _, _ in images}
        result = [c for c in candidates if id(c) in permitted or getattr(c, "kind", "") != "image"]
        return result, len(candidates) - len(result)

    # Never let a CMS hero override a strongly bound actual image. In a logo
    # story one correct, named visual beats any number of decorative pictures.
    best = max(images, key=lambda row: (row[1],
                                        bool(getattr(row[0], "schema_verified", False)),
                                        bool(getattr(row[0], "page_declared", False)),
                                        -row[2]))[0]
    output = [best]
    # Video source links are added separately by publisher and do not need
    # unrelated thumbnail images to accompany them.
    return output, len(candidates) - len(output)
