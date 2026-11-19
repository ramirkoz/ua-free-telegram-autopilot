"""2.3.44 owner RED: mundane repair and consumer roundup are not news.

Source-owned, deterministic, channel-role scoped. This runs before paid AI and
again on preexisting READY rows at the Telegram publication boundary.
No source/domain blacklist, no AI calls, no operator settings mutations.
"""
from __future__ import annotations

import re
from typing import Any


def _field(article: Any, key: str) -> str:
    try:
        return str(article[key] or "")
    except (KeyError, IndexError, TypeError):
        return str(getattr(article, key, "") or "")


# Single-digit collections are important: "8 Japanese Gifts" bypassed the
# former >=10-items rule, while "best/top gifts" did not match its headline.
_NUMBERED_GIFT_TITLE = re.compile(r"(?iu)^\s*[1-9]\d?\s+(?:[^.!?\n]{0,85}?)\bgifts?\b")
_GIFT_GUIDE_TITLE = re.compile(
    r"(?iu)\b(?:gift(?:ing)?\s+guide|gift\s+ideas|gift\s+roundup|"
    r"(?:best|top|perfect|thoughtful|favorite|favourite)\s+(?:[^.!?\n]{0,55}\s)?gifts?\b|"
    r"(?:gifts?|presents?)\s+for\s+(?:men|women|him|her|dad|mom|mothers?|fathers?|"
    r"boyfriends?|girlfriends?|husbands?|wives|designers?|kids|everyone)\b)"
)
_GIFT_BODY_LIST = re.compile(
    r"(?iu)\b(?:these|our|the)\s+(?:\d{1,2}|five|six|seven|eight|nine|ten|"
    r"eleven|twelve|twenty)\s+(?:picks?|gifts?|designs?|selections?|items?)\b|"
    r"\b(?:what\s+we\s+(?:like|dislike)|gift\s+ideas|gift\s+guide|"
    r"our\s+picks|shopping\s+list|choose\s+(?:around|from)|"
    r"for\s+(?:the\s+)?(?:boyfriend|husband|man|woman)\s+who)\b"
)
_NUMBERED_BODY_ITEMS = re.compile(r"(?m)^\s*[1-9]\d?[.)]\s+[^\n]{3,}")

_SAUCE_TOPIC = re.compile(r"(?iu)\b(?:sauces?|dips?|condiments?|соус\w*|підлив\w*)\b")
_SAUCE_RANKING = re.compile(
    r"(?iu)\b(?:ranked|ranking|best|worst|taste[ -]?test(?:ed|ing)?|"
    r"compared?|comparison|versus|vs\.?|better|top\s+\d+|"
    r"рейтинг\w*|найкращ\w*|найгірш\w*|порівня\w*|"
    r"добірк\w*|топ\s*\d+)\b"
)

_MEME_TOPIC = re.compile(r"(?iu)\b(?:memes?|меми|мемів|мемами)\b")
_MEME_ROUNDUP = re.compile(
    r"(?iu)(?:^\s*\d{1,3}\s+[^\n.!?]{0,95}\bmemes?\b|"
    r"\b(?:memes?|меми|мемів)\b[^\n.!?]{0,90}\b(?:roundup|collection|gallery|"
    r"compilation|ranked|list|добірк\w*|підбірк\w*|збірк\w*|\d{2,3})\b|"
    r"\b(?:best|top|random|relatable|hilarious|funniest)\b[^\n.!?]{0,85}\bmemes?\b|"
    r"\b\d{1,3}\s+memes?\b)"
)
_MEME_GALLERY = re.compile(r"(?m)^\s*#\d{1,3}\s*$")

_ROUTINE_REPAIR_TITLE = re.compile(
    r"(?iu)(?:\b(?:how\s+to|ways?\s+to|tips?\s+for)\s+(?:[^.!?\n]{0,35}\s)?"
    r"(?:repair|fix|restore|refurbish|service|clean)\b|"
    r"\b(?:repairing|restoring|refurbishing|fixing|teardown|tear[ -]?down|"
    r"disassembl\w*|restoration)\b|"
    r"\bsaving\s+(?:an?\s+)?(?:old|vintage)\s+[^.!?\n]{0,85}\b(?:scrap|trash|dump|landfill)\b|"
    r"\b(?:ремонт\w*|лагодж\w*|розбиран\w*|відновленн\w*\s+стар\w*)\b)"
)
_REPAIR_PHYSICAL_OBJECT = re.compile(
    r"(?iu)\b(?:device|gadget|smartphone|phone|laptop|computer|electronics?|"
    r"power\s+supply|radio|camera|screen|display|battery|console|printer|"
    r"speaker|keyboard|router|watch|television|tv|drone|vehicle|car|engine|"
    r"tool|appliance|furniture|chair|table|vintage|old|ipad|iphone|macbook|"
    r"homeview|toy|headphone|motorcycle|record\s+player|turntable|"
    r"пристр\w*|телефон\w*|ноутбук\w*|телевізор\w*|мебл\w*)\b"
)
_ROUTINE_REPAIR_PROCEDURE = tuple(re.compile(x, re.I) for x in (
    r"\b(?:solder\w*|desolder\w*|capacitors?)\b",
    r"\b(?:screws?|glue|glued|adhesive|prying|unplug\w*)\b",
    r"\b(?:connectors?|mainboard|circuit\s+board|wiring)\b",
    r"\b(?:transformer|multimeter|variac|voltage|power\s+supply)\b",
    r"\b(?:replac\w*|repair\w*|fixing|restoring|disassembl\w*)\b",
    r"\b(?:tools?|open(?:ing)?\s+the|remove(?:d|s)?|cleaning)\b",
))
_REPAIR_PUBLIC_NEWS = re.compile(
    r"(?iu)\b(?:right[ -]to[ -]repair|repair\s+law|"
    r"(?:official|formal|published)\s+repairability\s+score|"
    r"(?:regulator|court|commission)\s+(?:orders?|rules?|bans?|fines?)|"
    r"(?:safety\s+)?recall\w*|"
    r"(?:breakthrough|first[ -]ever)\s+(?:in\s+)?(?:repair|recycl|battery|material)|"
    r"(?:new|redesigned|novel)\s+(?:user[ -])?(?:replaceable|modular)\s+"
    r"(?:battery|screen|module|design|component))\b"
)


def owner_reader_value_reason_2344(role: str, article: Any) -> str:
    """Block proven unoriginal listicles and mundane repairs, not real news."""
    if role not in {"science", "creative"}:
        return ""
    title = _field(article, "title")[:600]
    raw = _field(article, "raw_text")[:18000]
    if not title.strip() or not raw.strip():
        return ""

    if _ROUTINE_REPAIR_TITLE.search(title) and _REPAIR_PHYSICAL_OBJECT.search(title):
        if not _REPAIR_PUBLIC_NEWS.search(title + "\n" + raw[:4500]):
            signals = sum(bool(p.search(raw)) for p in _ROUTINE_REPAIR_PROCEDURE)
            if signals >= 2:
                return "EDITORIAL_MUNDANE_REPAIR_NOT_NEWS_2344"

    if role != "creative":
        return ""
    # A single inventive device marketed as a gift is NOT a gift collection.
    has_gift_title = bool(_NUMBERED_GIFT_TITLE.search(title) or _GIFT_GUIDE_TITLE.search(title))
    if has_gift_title and (
        _GIFT_BODY_LIST.search(raw)
        or len(_NUMBERED_BODY_ITEMS.findall(raw)) >= 2
        or bool(_NUMBERED_GIFT_TITLE.search(title))
    ):
        return "CREATIVE_GIFT_ROUNDUP_NOT_NEWS_2344"

    if _SAUCE_TOPIC.search(title) and _SAUCE_RANKING.search(title):
        return "CREATIVE_SAUCE_RANKING_NOT_NEWS_2344"

    if _MEME_TOPIC.search(title) and (
        _MEME_ROUNDUP.search(title)
        or len(_MEME_GALLERY.findall(raw[:12000])) >= 3
    ):
        return "CREATIVE_MEME_COMPILATION_NOT_NEWS_2344"
    return ""
