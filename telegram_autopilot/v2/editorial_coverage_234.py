"""2.3.4 evidence-gated reconsideration of editorial false negatives.

A CHANNEL-FIT weak-audience-hook classification can be mistaken even for a
source-complete public-interest story. This module only nominates candidates
for an INDEPENDENT value model, and never approves a publication by itself.
Dedupe, factual QA, source origin and Telegram media are untouched.
"""
from __future__ import annotations

import re
from typing import Any

from .editorial_hard_floor import facts

_SCIENCE_PUBLIC_NEWS = re.compile(
    r"(?iu)\b(?:scientists?|researchers?|stud(?:y|ies)|discov(?:er|ery|ered)|"
    r"neuroscien\w*|brain|clinical\s+trial|medical\s+(?:research|study)|"
    r"astronom\w*|planet\w*|spacecraft|experiment|"
    r"science|evidence|breakthrough|"
    r"вчен\w*|досліджен\w*|відкрит\w*|експеримент\w*|"
    r"моз\w*|нейро\w*|медичн\w*|космічн\w*|планет\w*)\b"
)
_CYBER_PUBLIC_HARM = re.compile(
    r"(?iu)\b(?:malicious|malware|ransomware|breach|security\s+flaw|"
    r"vulnerabilit\w*|stolen\s+(?:data|credentials)|"
    r"фішинг\w*|вразлив\w*|шкідлив\w*|виток\w*\s+дан\w*|"
    r"викраден\w*\s+дан\w*)\b"
)
_TRADE_ONLY = re.compile(
    r"(?iu)\b(?:ipo|prospectus|shareholder|investor\s+relations|"
    r"quarterly\s+earnings|stock\s+price|new\s+firmware|"
    r"driver\s+update|benchmark|overclock|"
    r"бірж\w*|акціонер\w*|фінансов\w*\s+звіт)\b"
)
_COMMERCIAL_STORY = re.compile(
    r"(?iu)\b(?:viral|collab\w*|unexpected|unusual|meme|campaign|"
    r"consumer\w*|shoppers?|retail|cultural|pop\s*culture|"
    r"stunt|backlash|brand\w*|ad(?:vertising)?\s+campaign|"
    r"limited\s+edition|prank|viral|"
    r"колаборац\w*|вірусн\w*|мем\w*|бренд\w*|кампані\w*|"
    r"незвичайн\w*|споживач\w*|культурн\w*|рекламн\w*)\b"
)


def _get(article: Any, key: str) -> str:
    try:
        return str(article[key] or "")
    except (KeyError, IndexError, TypeError):
        return str(getattr(article, key, "") or "")


def eligible_recheck_234(article: Any, *, lane: str, rejection: str) -> bool:
    """Only complete, factual source articles with a recoverable audience angle.

    No rescue for source shortness, hard bans, unsupported evidence, duplicates,
    routine promotional PR, or old material. Called *after* existing hard gates.
    """
    if rejection != "weak_audience_hook" or lane not in {"science", "commercial"}:
        return False
    title = _get(article, "title").strip()
    body = _get(article, "raw_text").strip()
    if len(title) < 22 or len(body) < 420 or len(facts(body)) < 2:
        return False
    if lane == "science":
        if _TRADE_ONLY.search(title):
            return False
        return bool(_SCIENCE_PUBLIC_NEWS.search(title) or _CYBER_PUBLIC_HARM.search(title))
    # Commercial value recheck is NOT for brand-only wire announcements.
    # The separate value gate and source quote veto remain decisive.
    return bool(_COMMERCIAL_STORY.search(title))


def independent_value_confirms_234(value: dict, *, lane: str) -> bool:
    """High independent evidence requirements, never a permissive default."""
    def score(key: str) -> int:
        try:
            return max(0, min(100, int(float(value.get(key, 0) or 0))))
        except (TypeError, ValueError):
            return 0
    if lane == "science":
        return (value.get("curiosity_only") is not True
                and score("reader_payoff") >= 67
                and score("retellability") >= 65
                and max(score("consequence_or_insight"), score("concrete_stakes")) >= 62)
    if lane == "commercial":
        return (score("general_interest") >= 70
                and score("retellability") >= 68
                and max(score("culture_signal"), score("surprise_or_conflict"),
                        score("consumer_relevance")) >= 65)
    return False


def science_finding_evidence_234(article: Any) -> bool:
    """Source-level evidence for a narrow science VALUE threshold adjustment.

    This cannot override a selector REJECT or a safety/fact veto.
    """
    return eligible_recheck_234(article, lane="science", rejection="weak_audience_hook")


def strong_commercial_story_evidence_234(article: Any, value: dict) -> bool:
    """Source-exact supporting quote is required for the cultural-story lane."""
    try:
        from .commercial_reader_256 import normalized_reader_signal_256
        signal = normalized_reader_signal_256(value)
        if (not signal["shareable_to_friend"] or signal["product_only"] or
            signal["story_class"] not in {"viral_culture", "brand_stunt",
                "unexpected_use", "human_behavior", "surprising_research",
                "remarkable_object"}):
            return False
        quote = " ".join(signal["share_hook_quote"].casefold().split())
        original = " ".join((_get(article, "title") + " " +
                             _get(article, "raw_text")).casefold().split())
        return len(quote) >= 18 and quote in original
    except Exception:
        return False
