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


# 2.3.29: source-owned high-precision retail-roundup gate.  This is *not*
# a blanket veto on product news, field tests or genuine new inventions.
# Requiring both a shopping-list title and independent retail body signals
# avoids vetoing ordinary scientific comparisons and engineering discoveries.
_RETAIL_LIST_TITLE = re.compile(
    r"(?iu)(?:\b(?:the\s+)?\d{1,2}\s+(?:best|top)\s+(?:[\w-]+\s+){0,5}"
    r"|^\s*(?:the\s+)?best\s+(?:[\w-]+\s+){1,7}(?:to\s+buy|of\s+20\d\d|for\s+[\w-]+)"
    r"|\b(?:top|best)\s+\d{1,2}\s+(?:[\w-]+\s+){1,6})"
)
_RETAIL_AFFILIATE = re.compile(
    r"(?iu)(?:we\s+may\s+earn\s+(?:a\s+)?commission|"
    r"earn\s+commissions?\s+(?:if|when|from)|"
    r"affiliate\s+links?|"
    r"комісі\w*\s+за\s+(?:покупк|посилан))"
)
_RETAIL_RANKED = re.compile(
    r"(?iu)(?:\bbest\s+(?:overall|value|budget|for\s+(?:large|small)|"
    r"(?:two|single)[-\s]stage)\b|"
    r"найкращ\w*\s+(?:в\s+цілому|за\s+ціною|бюджетн))"
)
_RETAIL_METHOD = re.compile(
    r"(?iu)(?:\bhow\s+we\s+(?:selected|chose|tested|picked)\b|"
    r"\bour\s+(?:picks|top\s+picks|recommendations)\b|"
    r"\bwhat\s+to\s+consider\b|"
    r"\b(?:shopping|buying)\s+guide\b|"
    r"як\s+ми\s+(?:обирали|тестували))"
)


def science_retail_buying_guide_reason_2329(article: Any) -> str:
    """A store roundup is not CTRL+UA news, even with electric/battery words.

    Restrict the hard stop to a source headline explicitly promising a list
    of recommended products, confirmed by TWO independent retail body cues.
    """
    def get(key: str) -> str:
        try:
            return str(article[key] or "")
        except (KeyError, IndexError, TypeError):
            return str(getattr(article, key, "") or "")

    title = get("title").strip()
    if not _RETAIL_LIST_TITLE.search(title):
        return ""
    raw = get("raw_text")[:35000]
    retail_cues = sum(bool(pattern.search(raw)) for pattern in (
        _RETAIL_AFFILIATE, _RETAIL_RANKED, _RETAIL_METHOD
    ))
    if retail_cues >= 2:
        return "SCIENCE_RETAIL_BUYING_GUIDE_2329"
    return ""


def editorial_source_topic_reason_2319(channel: Any, article: Any) -> str:
    """Do not call ordinary career/lifestyle advice scientific discovery.

    Only highly specific observed title forms are blocked. Broad technology
    explainers, useful inventions and positive human-reviewed stories must
    remain eligible under editorial QA and the existing safety checks.
    """
    if getattr(channel, "mode", None) != ChannelMode.EDITORIAL:
        return ""
    if calibrated_editorial_role(channel) != "science":
        return ""
    try:
        title = str(article["title"] or "")
    except (KeyError, IndexError, TypeError):
        title = str(getattr(article, "title", "") or "")
    if _NONTECH_WORKPLACE_ADVICE.search(title):
        return "SCIENCE_NONTECH_WORKPLACE_ADVICE_2319"
    retail_problem = science_retail_buying_guide_reason_2329(article)
    if retail_problem:
        return retail_problem
    return ""
