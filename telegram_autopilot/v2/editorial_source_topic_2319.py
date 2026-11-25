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
    # 2.3.45: no recipes or cooking tips in editorial channels; check source
    # before any paid AI and repeat through the same READY/publication gate.
    from .editorial_owner_2345 import absolute_recipe_reason_2345
    recipe_2345 = absolute_recipe_reason_2345(article)
    if recipe_2345:
        return recipe_2345
    # 2.3.39: owner-rejected ordinary rescue stories are not creative news.
    # Source-only veto runs both before paid AI and at the final READY gate.
    if role == "creative":
        from .editorial_live_2341 import creative_ordinary_cooking_recipe_reason_2341
        recipe = creative_ordinary_cooking_recipe_reason_2341(article)
        if recipe:
            return recipe
        from .editorial_live_2339 import creative_routine_pet_rescue_reason
        rescue = creative_routine_pet_rescue_reason(article)
        if rescue:
            return rescue
    # 2.3.54: owner-reviewed retail/obituary and story-video requirements.
    # This is a source-only check; it is repeated at the final READY gate.
    from .editorial_owner_2354 import owner_source_veto_2354
    owner_2354 = owner_source_veto_2354(role, article)
    if owner_2354:
        return owner_2354
    # 2.3.56: evidence-conjunctive seasonal shelf/price press release. The
    # same source-topic function is called at the READY/send boundary; never
    # ban a food/brand or a genuinely novel product in general.
    if role == "creative":
        from .editorial_quality_2356 import creative_routine_product_reason_2356
        routine_2356 = creative_routine_product_reason_2356(article)
        if routine_2356:
            return routine_2356
    # 2.3.35: operator-red false-positive controls, topic only; no fact bypass.
    from .editorial_owner_235 import owner_source_veto_235
    owner_veto = owner_source_veto_235(role, article)
    if owner_veto:
        return owner_veto
    # 2.3.30: independent, evidence-based audience boundary. This entrypoint
    # is shared by the pre-AI selector AND the final READY/publication gate.
    from .editorial_audience_2330 import editorial_audience_source_reason_2330
    audience_reason = editorial_audience_source_reason_2330(role, article)
    if audience_reason:
        return audience_reason
    from .editorial_owner_2332 import editorial_source_reason_2332
    new_reason = editorial_source_reason_2332(role, article)
    if new_reason:
        return new_reason
    # 2.3.44: preserve every established owner-veto reason first. The new
    # source-only owner rule closes uncovered categories before paid AI, and
    # this same hook runs again on legacy READY at the prepublish boundary.
    from .editorial_owner_2344 import owner_reader_value_reason_2344
    owner_reader_value = owner_reader_value_reason_2344(role, article)
    if owner_reader_value:
        return owner_reader_value
    if role != "science":
        return ""
    from .editorial_owner_2343 import science_procedural_teardown_reason_2343
    teardown = science_procedural_teardown_reason_2343(article)
    if teardown:
        return teardown
    try:
        title = str(article["title"] or "")
    except (KeyError, IndexError, TypeError):
        title = str(getattr(article, "title", "") or "")
    if _NONTECH_WORKPLACE_ADVICE.search(title):
        return "SCIENCE_NONTECH_WORKPLACE_ADVICE_2319"
    if _is_retail_buying_guide(article):
        return "SCIENCE_AFFILIATE_BUYING_GUIDE_2329"
    return ""
