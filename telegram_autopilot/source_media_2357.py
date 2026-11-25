"""Choose an editorial lead using source evidence, not download order."""
from __future__ import annotations
import re


def video_has_story_proof(item, title: str, article_text: str) -> bool:
    from .media_pipeline import _semantic_media_evidence, _video_story_signal, _site_widget_media_2330
    if item.kind not in {"video", "iframe"} or _site_widget_media_2330(item):
        return False
    title_hits, body_hits, _ = _semantic_media_evidence(item, title=title, article_text=article_text)
    # Explicit source-owned video + specific description. A generic video word
    # in the article or a gallery flag alone is never proof.
    if item.linked_page_url and not (item.schema_verified or item.featured):
        return False
    if title_hits >= 2 or (title_hits >= 1 and body_hits >= 3):
        return True
    if item.schema_verified and (title_hits >= 1 or body_hits >= 2):
        return True
    # A publisher's explicit featured player can be opaque (e.g. Vimeo ID).
    return bool(item.featured and item.context == "featured video" and _video_story_signal(title, ""))


_SCHEMATIC = re.compile(r"\b(?:render(?:ing|s)?|mockup|mock-up|diagram|schematic|sketch|concept art|technical drawing|illustration|floor plan|visualisation|visualization)\b", re.I)
_PORTRAIT = re.compile(r"\b(?:portrait|headshot|profile photo)\b", re.I)
_REAL = re.compile(r"\b(?:installed|installation|completed|on site|on-site|in situ|realised|realized|photograph|station interior|street view|finished)\b", re.I)
_COMPARISON = re.compile(r"\b(?:before and after|before-and-after|side.by.side|compare(?:s|d)?|comparison)\b", re.I)


def choose_editorial_media(candidates, title: str, article_text: str):
    from .media_pipeline import _semantic_media_evidence, _evidence_text, _video_story_signal
    items = [x for x in candidates if x is not None and x.kind in {"image", "video"} and x.url]
    if not items:
        return []
    def score(x):
        evidence = _evidence_text(x)
        title_hits, body_hits, _ = _semantic_media_evidence(x, title=title, article_text=article_text)
        s = float(x.relevance_score) + min(30, title_hits * 10) + min(12, body_hits * 2)
        if _REAL.search(evidence): s += 24
        if _SCHEMATIC.search(evidence): s -= 28
        if _PORTRAIT.search(evidence) and title_hits < 2: s -= 22
        if x.kind == "video":
            s += 35 if _video_story_signal(title, "") else -10
        return (s, -x.position, x.width * x.height)
    ranked = sorted(items, key=score, reverse=True)
    # Exceptional two-image comparison only if the source explicitly frames it
    # as such and independently labels both before and after.
    if _COMPARISON.search(title):
        before = [x for x in ranked if x.kind == "image" and re.search(r"\bbefore\b", _evidence_text(x), re.I)]
        after = [x for x in ranked if x.kind == "image" and re.search(r"\bafter\b", _evidence_text(x), re.I)]
        if before and after and before[0].url != after[0].url:
            return [before[0], after[0]]
    return ranked[:1]
