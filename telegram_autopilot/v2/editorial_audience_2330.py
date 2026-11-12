"""v2.3.30: source-proven, high-precision reader-value vetoes.

The source's country, brand, price, foreign language or publisher are NOT
standalone exclusion criteria.  Only narrow conjunctions from actual owner-
rejected LIVE articles are hard-blocked. Genuine science, inventions, design,
creative campaigns and relevant international news remain eligible.

Called by editorial_source_topic_reason_2319 before paid AI and by the same
function inside hard_editorial_reject at the final Telegram boundary, including
READY created on an older build.  No database changes or remote calls.
"""
from __future__ import annotations

import re
from typing import Any


def _source(article: Any, key: str) -> str:
    try:
        return str(article[key] or "")
    except (KeyError, IndexError, TypeError):
        return str(getattr(article, key, "") or "")


# Science: a narrow consumer-market availability/price commentary with no
# laboratory result or technical invention.  Do not veto e-mobility R&D,
# battery research, real innovations or a country merely being outside Ukraine.
_MARKET_CONSUMER_TITLE = re.compile(
    r"(?iu)\b(?:electric|battery[- ]powered)\s+(?:moped|scooter|motorbike)\b"
    r"|\b(?:електро(?:мопед|скутер)|акумуляторн\w+\s+скутер)\b"
)
_MARKET_ACCESS_TITLE = re.compile(
    r"(?iu)(?:why\s+can['’]?t\s+(?:americans|we)\s+buy\s+it|"
    r"why\s+.*\s+(?:not\s+)?(?:sold|available)\s+in\s+(?:the\s+)?u\.?s\.?|"
    r"(?:американц\w*|сша).{0,70}(?:не\s+можуть\s+купити|не\s+прода\w*))"
)
_MARKET_PRICE = re.compile(r"(?iu)(?:\$\s*[\d,]{3,}|\b\d{3,}\s*(?:usd|долар\w*))")
_MARKET_GEO = re.compile(r"(?iu)\b(?:vietnam|viet\s*nam|в['’]?єтнам\w*|u\.?s\.?a?\b|американ\w*|сша)\b")
_MARKET_SALES = re.compile(
    r"(?iu)(?:\b(?:price|prices|pricing|costs?|market|local\s+markets|sell|sold|sales|availability|buyers?)\b"
    r"|ціна|продаж\w*|ринок|покупц\w*)"
)

# Science: a routine aftermarket processor-contact accessory, not a finding
# about nanomaterials. The term "nanotube" alone is NOT evidence of an advance.
_PC_CONTACT_ACCESSORY = re.compile(
    r"(?iu)(?:thermal\s+(?:pad|paste|interface)|"
    r"термо(?:прокладк|паст|інтерфейс)\w*)"
)
_PC_SOCKET = re.compile(
    r"(?iu)\b(?:processors?|cpus?|amd|intel|am[45]|lga\d{3,5}|"
    r"motherboards?|socket|процесор\w*|сокет\w*)\b"
)
_PC_RETAIL = re.compile(
    r"(?iu)(?:\$\s*\d+(?:\.\d+)?|"
    r"\b(?:buy|purchase|price|costs?|performance\s+for|maintenance[- ]free)\b|"
    r"грн|продаж\w*|вартіст\w*|ціна)"
)

# Creative: local overseas election / politician's personal/legal story with
# merely incidental YouTube virality is not an artistic or creative story.
_MUNICIPAL_ELECTION = re.compile(
    r"(?iu)(?:\b(?:city|town|municipal)\s+council\b|"
    r"\b(?:city\s+)?council(?:member|or|woman|man)\b|"
    r"міськ\w+\s+рад\w*|муніципальн\w+\s+рад\w*)"
)
_ELECTED = re.compile(
    r"(?iu)\b(?:elected|re-?elected|wins?\s+(?:another\s+)?election|"
    r"сенатор\w*|обрал\w*|переобрал\w*)\b"
)
_OFFICE_HOLDER = re.compile(
    r"(?iu)\b(?:senator|former\s+senator|state\s+senate|politician|"
    r"political\s+office|сенатор\w*|політик\w*)\b"
)
_CREATIVE_ACTUAL_WORK = re.compile(
    r"(?iu)(?:\b(?:art\s+installation|artwork|original\s+design|"
    r"documentary\s+film|animated\s+film|satirical\s+ad|creative\s+campaign)\b|"
    r"мистецьк\w+\s+інсталяці\w*|авторськ\w+\s+дизайн\w*|"
    r"документальн\w+\s+фільм\w*|креативн\w+\s+кампані\w*)"
)


# Full 1472 original owner label + RAW SOURCE replay (12.11.2026):
# 24/153 science negatives were unmistakable discount/coupon/Black-Friday
# shopping posts; ZERO of 352 owner-positive science posts matched both title
# and source-body commercial proof. No blanket retail keyword exclusion.
_SCIENCE_RETAIL_PROMO_TITLE_2330 = re.compile(
    r"(?iu)(?:\bblack\s+friday\b|\bon\s+sale\b|"
    r"\b(?:on|at|for)\s+(?:a\s+)?discount\b|\b\d{1,2}%\s+off\b|"
    r"\b\$\s*\d[\d,]*(?:\.\d+)?\s+off\b|"
    r"\b(?:best|top)\s+\w+\s+deals?\b|\bbuy\s+now\b|"
    r"\b(?:early|latest)\s+deals?\b|"
    r"\b(?:is|are|gets?|got|now)\s+\$\s*\d+\s+off\b|"
    r"\b(?:savings?|coupon|promo\s+code|discount\s+codes?)\b|"
    r"\b(?:deals|promo\s+codes?)\s+(?:for|on|at|in|under)\b)"
)
_RETAIL_SOURCE_PROOF_2330 = re.compile(
    r"(?iu)(?:\b(?:discount|save|buy|sale|shop|deal|order|price|"
    r"black\s+friday|coupon|cart|checkout)\b|\$\s*\d{1,})"
)

# The same four-workbook source replay found 16 routine agency personnel/
# account-move announcements among 149 owner-rejected creative stories,
# with ZERO of 146 selected creative stories caught. This is NOT a blacklist
# of advertising agencies; genuine original campaigns/designs still pass.
_CREATIVE_PERSONNEL_PR_TITLE_2330 = re.compile(
    r"(?iu)\b(?:appoints?|appointed|names?|hires?|hired|promotes?|"
    r"recruits?|departs?|steps\s+down|"
    r"joins?\s+(?:the\s+)?(?:team|agency|as)\b|leadership\s+hires?)\b"
)
_CREATIVE_PERSONNEL_PR_BODY_2330 = re.compile(
    r"(?iu)\b(?:agency|creative|campaign|marketing|advertis|"
    r"business|leadership|executive|managing|director|team)\b"
)
_CREATIVE_RETAIL_PROMO_TITLE_2330 = re.compile(
    r"(?iu)(?:\bsave\s+\d+%|\b\d{1,2}%\s+off|"
    r"up\s+to\s+\$\d+\s+off|"
    r"\bblack\s+friday\s+deals?\b|coupon\s+code|"
    r"\bget\s+\d+%\s+off|\bbest\s+gifts\s+under\b)"
)


def editorial_audience_source_reason_2330(role: str, article: Any) -> str:
    """Return a precise reject reason only when *source* proves a weak story.

    There is deliberately no generic list of countries, brands or hard-to-
    quantify "audience interest" numbers. AI judges other borderline stories
    with the operator's real examples; this guard captures verified mistakes.
    """
    if role not in {"science", "creative"}:
        return ""
    title = _source(article, "title")[:1500]
    body = _source(article, "raw_text")[:28000]
    if not title or not body:
        return ""
    lead = body[:5500]
    if role == "science":
        if (_SCIENCE_RETAIL_PROMO_TITLE_2330.search(title)
                and _RETAIL_SOURCE_PROOF_2330.search(body[:12000])):
            return "SCIENCE_RETAIL_PROMOTION_2330"
        if (_MARKET_CONSUMER_TITLE.search(title)
                and _MARKET_ACCESS_TITLE.search(title)
                and _MARKET_PRICE.search(title)
                and _MARKET_GEO.search(lead)
                and _MARKET_SALES.search(lead)):
            return "SCIENCE_ROUTINE_FOREIGN_CONSUMER_AVAILABILITY_2330"
        if (_PC_CONTACT_ACCESSORY.search(title)
                and _PC_SOCKET.search(title)
                and _PC_RETAIL.search(title)
                and _PC_SOCKET.search(lead)):
            return "SCIENCE_NICHE_PC_ACCESSORY_RELEASE_2330"
    elif role == "creative":
        if (_CREATIVE_PERSONNEL_PR_TITLE_2330.search(title)
                and _CREATIVE_PERSONNEL_PR_BODY_2330.search(lead)):
            return "CREATIVE_AGENCY_PERSONNEL_PR_2330"
        if (_CREATIVE_RETAIL_PROMO_TITLE_2330.search(title)
                and _RETAIL_SOURCE_PROOF_2330.search(body[:12000])):
            return "CREATIVE_RETAIL_PROMOTION_2330"
        if (_MUNICIPAL_ELECTION.search(body)
          and _ELECTED.search(title)
          and _OFFICE_HOLDER.search(title + "\n" + lead)
                and not _CREATIVE_ACTUAL_WORK.search(title + "\n" + lead)):
            return "CREATIVE_OFFTOPIC_LOCAL_ELECTION_2330"
    return ""
