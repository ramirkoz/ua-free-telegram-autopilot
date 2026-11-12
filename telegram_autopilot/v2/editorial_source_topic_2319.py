"""2.3.19 conservative CTRL+UA source-topic gate from verified LIVE false positive."""
from __future__ import annotations

import re
from typing import Any

from .domain import ChannelMode
from .editorial_human_calibration_236 import calibrated_editorial_role


_NONTECH_WORKPLACE_ADVICE = re.compile(
    r"(?iu)(?:how\s+to\s+remind\s+(?:your\s+)?boss\s+about\s+(?:your\s+)?vacation"
    r"|how\s+to\s+ask\s+(?:your\s+)?boss\s+for\s+time\s+off"
    r"|як\s+нагадати\s+керівникові\s+про\s+відпустку)"
)



# Title alone is not a veto. Require independent shopping cues in SOURCE body,
# not a rewritten draft, the publisher's reputation, or a page URL.
_RETAIL_TITLE = re.compile(
    r"(?iu)(?:\b(?:the|our|these|top)\s+\d{1,2}\s+(?:best|top)\b"
    r"|\b\d{1,2}\s+best\b"
    r"|\b(?:best|top)\s+\d{1,2}\s+\S+"
    r"|\b(?:the|our)\s+best\s+\S+"
    r"|\b(?:buying|buyers?)\s+guide\b"
    r"|\b(?:best|top)\s+.{2,65}\s+(?:to\s+buy|for\s+your|of\s+20\d{2})\b"
    r"|\b(?:найкращ\w*|топ[- ]?\d{1,2})\s+.{2,65}\s+(?:купити|для\s+покупки|20\d{2})\b)"
)
_RETAIL_AFFILIATE = re.compile(
    r"(?iu)\b(?:we\s+may\s+earn\s+(?:a\s+)?commission"
    r"|earn\s+(?:a\s+)?commission\s+if\s+you\s+buy"
    r"|affiliate\s+links?|affiliate\s+commission"
    r"|commission\s+(?:if|when)\s+you\s+buy"
    r"|комісі\w*\s+за\s+(?:покупк|купівл))\b"
)
_RETAIL_BADGE = re.compile(
    r"(?iu)\b(?:best\s+(?:overall|value|budget|buy|premium|pick|for\s+[a-z][\w-]*)"
    r"|top\s+pick|editor'?s\s+pick"
    r"|найкращ\w*\s+(?:бюджетн|загалом|вибір))\b"
)
_RETAIL_SHOP = re.compile(
    r"(?iu)\b(?:how\s+we\s+(?:selected|tested|chose)"
    r"|what\s+to\s+consider|our\s+(?:top\s+)?picks"
    r"|we\s+recommend\s+(?:these\s+)?models"
    r"|shop\s+now|buy\s+now|add\s+to\s+cart"
    r"|where\s+to\s+buy|our\s+selections\s+for\s+this\s+list"
    r"|як\s+ми\s+(?:обирали|тестували)|де\s+купити)\b"
)


def _article_value(article: Any, key: str) -> str:
    try:
        return str(article[key] or "")
    except (KeyError, IndexError, TypeError):
        return str(getattr(article, key, "") or "")


def _is_retail_buying_guide(article: Any) -> bool:
    if not _RETAIL_TITLE.search(_article_value(article, "title")):
        return False
    source = _article_value(article, "raw_text")
    if not source:
        return False
    ranks = {m.group(0).casefold() for m in _RETAIL_BADGE.finditer(source)}
    independent_signals = (
        bool(_RETAIL_AFFILIATE.search(source)),
        len(ranks) >= 2,
        bool(_RETAIL_SHOP.search(source)),
    )
    return sum(independent_signals) >= 2


def editorial_source_topic_reason_2319(channel: Any, article: Any) -> str:
    """Do not call ordinary career/lifestyle advice scientific discovery.

    Only highly specific observed title forms are blocked. Broad technology
    explainers, useful inventions and positive human-reviewed stories must
    remain eligible under editorial QA and the existing safety checks.
    """
    if getattr(channel, "mode", None) != ChannelMode.EDITORIAL:
        return ""
    role = calibrated_editorial_role(channel)
    if role not in {"science", "creative"}:
        return ""
    # 2.3.30: independent, evidence-based audience boundary. This entrypoint
    # is shared by the pre-AI selector AND the final READY/publication gate.
    from .editorial_audience_2330 import editorial_audience_source_reason_2330
    audience_reason = editorial_audience_source_reason_2330(role, article)
    if audience_reason:
        return audience_reason
    if role != "science":
        return ""
    try:
        title = str(article["title"] or "")
    except (KeyError, IndexError, TypeError):
        title = str(getattr(article, "title", "") or "")
    if _NONTECH_WORKPLACE_ADVICE.search(title):
        return "SCIENCE_NONTECH_WORKPLACE_ADVICE_2319"
    if _is_retail_buying_guide(article):
        return "SCIENCE_AFFILIATE_BUYING_GUIDE_2329"
    return ""
