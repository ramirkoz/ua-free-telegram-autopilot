"""2.3.54 source-evidenced editorial mistakes confirmed by the channel owner.

Only conjunctions from the original source are hard stops.  No brand,
publication, country, food category, or one-word video blacklist.  The
accepted 21-post operator cohort remains eligible.  This module makes no
network requests, never alters an operator database, and never sends media.
"""
from __future__ import annotations

import re
from typing import Any

from .media_pipeline import build_media_bundle


def _field(article: Any, field: str) -> str:
    try:
        return str(article[field] or "")
    except (KeyError, IndexError, TypeError):
        return str(getattr(article, field, "") or "")


_DISCOUNT_HEAD = re.compile(
    r"(?iu)(?:\$\s*\d+(?:\.\d+)?\s+(?:price\s+cut|off|discount)\b"
    r"|\b(?:price\s+cut|deal|discount|coupon|black\s+friday)\b.{0,70}"
    r"\b(?:before\s+thanksgiving|on\s+sale|this\s+week|\d+\s*%\s+off)\b"
    r"|\b\d{1,2}\s*%\s+off\b)"
)
_DISCOUNT_BODY = re.compile(
    r"(?iu)(?:click\s+here\s+to\s+buy|\bbuy\s+now\b|\bprice\s+cut\b|"
    r"\b\d{1,2}\s*%\s+off\b|\bblack\s+friday\b|\b(?:sale|discount)\s+price\b)"
)
_PRICE_PAIR = re.compile(r"(?iu)(?:\$\s*\d[\d,.]*.{0,32}\$\s*\d[\d,.]*|\b\d{1,2}\s*%\s+off\b)")

_FOOD_RETURN = re.compile(
    r"(?iu)\b(?:brought\s+back|back\s+on\s+shelves|returns?\s+to\s+(?:the\s+)?(?:shelves|stores?|menu)|"
    r"back\s+(?:in|at)\s+(?:stores?|stock|the\s+prepared\s+foods?\s+section))\b"
)
_ROUTINE_SIDES = re.compile(
    r"(?iu)\b(?:pre[- ]made\s+sides?|prepared\s+(?:side\s+dishes|foods?)|"
    r"ready[- ]made\s+sides?|mashed\s+potatoes|lobster\s+mac\s+(?:and|&)\s+cheese)\b"
)
_SHOPPING_REVIEW = re.compile(
    r"(?iu)\b(?:worth\s+your\s+money|customers?\s+(?:say|think)|"
    r"customer\s+reviews?|shoppers?\s+(?:say|think)|buy(?:ing)?\s+it|"
    r"(?:holiday|thanksgiving)\s+(?:cooking|spread)|prepared\s+foods?\s+section)\b"
)

_OBIT_HEAD = re.compile(
    r"(?iu)^\s*(?:vale\s*[,!:]|in\s+memoriam\b|obituary\s*[:—-]|"
    r"remembering\s+.{4,100}(?:scientist|ecologist|physicist|researcher|professor)|"
    r".{4,115}\b(?:grieves?\s+the\s+loss|dies\s+at\s+age|has\s+died|passes?\s+away)\b)"
)
_OBIT_BODY = re.compile(
    r"(?iu)\b(?:has\s+lost|died\s+on|died\s+at|passed\s+away|"
    r"tributes?|celebrat(?:ory|ion)\s+of\s+(?:his|her|their)\s+life|"
    r"achievements\s+and\s+legacy|grieves?\s+the\s+loss)\b"
)

# A filmed *narrative advertisement* is a different artifact from a physical
# campaign stunt or designed product. Mere words 'video' or 'campaign' never
# impose a video requirement (owner accepted the cliff stunt and KFC GTA disc).
_FILM_AD = re.compile(
    r"(?iu)\b(?:released?|launched?|unveiled?|created?|premiered?)\s+"
    r"(?:an?\s+)?(?:new\s+)?(?:campaign\s+film|advertis(?:ing|ement)\s+film|"
    r"brand\s+film|commercial\s+(?:film|spot)|video\s+advert(?:isement)?)\b"
)
_FILM_NARRATIVE = re.compile(
    r"(?iu)\b(?:directed\s+by|director|centres?\s+around|centers?\s+on|"
    r"scene|plot|script|cinematic|groom|bride|storytelling|screenplay|"
    r"film\s+culture|shot\s+the\s+film)\b"
)


def story_needs_embedded_video_2354(role: str, article: Any) -> bool:
    """Require an actual uploadable clip, not a poster or bare YouTube URL.

    The condition intentionally depends on exact-source semantic evidence:
    an actual narrative campaign *film* plus story/film direction detail.
    This does not apply to general viral videos, product design, gaming
    stunts, food brand promotions or standalone campaign photographs.
    """
    if role != "creative":
        return False
    source = _field(article, "raw_text")[:9000]
    title = _field(article, "title")[:400]
    return bool(_FILM_AD.search(source) and _FILM_NARRATIVE.search(title + "\n" + source))


def video_story_media_reason_2354(role: str, article: Any) -> str:
    if not story_needs_embedded_video_2354(role, article):
        return ""
    bundle = build_media_bundle(article)
    if any(item.kind == "video" for item in bundle.items):
        return ""
    return "CREATIVE_FILM_VIDEO_ASSET_REQUIRED_2354"


def owner_source_veto_2354(role: str, article: Any) -> str:
    """Conservative source-only editorial choices from 24 Nov owner review."""
    if role not in {"creative", "science"}:
        return ""
    title = _field(article, "title")[:500]
    body = _field(article, "raw_text")[:12000]
    if not title or not body:
        return ""
    if role == "science":
        if _OBIT_HEAD.search(title) and _OBIT_BODY.search(body[:6500]):
            return "SCIENCE_OBITUARY_WITHOUT_NEW_RESULT_2354"
        return ""
    if (_DISCOUNT_HEAD.search(title) and _DISCOUNT_BODY.search(body)
            and (_PRICE_PAIR.search(body) or re.search(r"\$\s*\d+\s+(?:off|price\s+cut)", title, re.I))):
        return "CREATIVE_ROUTINE_DISCOUNT_ONLY_2354"
    if (_FOOD_RETURN.search(title) and _ROUTINE_SIDES.search(title + "\n" + body[:3500])
            and _SHOPPING_REVIEW.search(title + "\n" + body[:3500])):
        return "CREATIVE_ORDINARY_RETAIL_FOOD_2354"
    return video_story_media_reason_2354(role, article)


__all__ = ["owner_source_veto_2354", "story_needs_embedded_video_2354", "video_story_media_reason_2354"]
