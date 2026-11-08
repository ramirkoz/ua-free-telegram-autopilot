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
    return ""
