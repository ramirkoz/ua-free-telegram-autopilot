"""v2.3.32: source-backed operator vetoes from 142 actual v2.3.31 posts.

Only the immutable original title/body and the generated final text are inspected.
No source-name/geographic inferences, model/network calls, state writes or
Telegram actions. The source gate is applied before AI and before any READY send.
"""
from __future__ import annotations

import re
from typing import Any


def _v(article: Any, key: str) -> str:
    try:
        return str(article[key] or "")
    except (IndexError, KeyError, TypeError):
        return str(getattr(article, key, "") or "")


def _rx(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.I | re.U)


# The dangerous LIVE article has two *stitched* fragments without a verb:
# "Реактив між Шевчиком і Заводським. Мопед на Хортицький". Check each
# fragment first, without replacing 'reactive' and 'moped' with everyday
# transportation terminology; those words denote airborne threats in the
# regional alert feed. A completed strike/official consequence has a different
# verb ('влучив', 'пошкодив', etc) and must remain reportable.
_TACTICAL_WEAPON = _rx(r"\b(?:реактив(?:ний|ні|у|а|ів|ом)?|мопед(?:и|ів|ом|а)?|"
                      r"мопед\w*)\b")
_TACTICAL_DESTINATION = _rx(r"(?:\b(?:між|повз|над|через|"
                           r"курсом\s+на|напрям\w*|летить|рухається|проліта\w*)\b|"
                           r"\b(?:на|до|у|в)\s+(?:хортицьк\w*|заводськ\w*|"
                           r"шевчик\w*|оріхів\w*|бердянськ\w*|запоріжж\w*))")
_TACTICAL_SETTLED = _rx(r"\b(?:влучи\w*|збил\w*|збит\w*|знешкод\w*|"
                       r"перехоп\w*|пошкоджен\w*|зруйнован\w*|"
                       r"загинул\w*|поранен\w*|постраждал\w*|"
                       r"ліквідован\w*\s+пожеж\w*)\b")
_SOURCE_PROMO = _rx(r"(?:✉️?\s*надіслати\s+новину|"
                    r"https?://t\.me/\w+_bot|надiслати\s+новину)")

# The heading, not an unrelated footer mention of a locality, proves the
# subject. Do not reject a factual region-wide decision or current service
# change merely because it contains an official invitation/telephone number.
_DONATION_ASK = _rx(r"(?:\bзбір\s+на\s+(?:ecoflow|зарядн\w*\s+станц)|"
                   r"підтримат\w*\s+збір|долучит\w*\s+до\s+збору|"
                   r"мета\s+збору\s*:\s*[\d\s]+\s*грн)")
_FUNDRAISE_CONTEXT = _rx(r"(?:прос\w*\s+(?:по\s+)?допомог\w*|"
                        r"переказ\w*|посилання\s+на\s+банку|"
                        r"кожна\s+гривня|долуч\w*\s+сум\w*|"
                        r"картк\w*\s*:\s*\d{8,})")
_FAREWELL_NOTICE = _rx(r"(?:\bвідбудеться\s+прощання\b|"
                      r"запрошу\w*\s+на\s+прощання|"
                      r"\bпроща\w*\s+відбудеться\b)")
_HOTLINE_NOTICE = _rx(r"(?:прям\w*\s+(?:«?гаряч\w*»?\s+)?(?:телефонн\w*\s+)?ліні\w*|"
                    r"гаряч\w*\s+телефонн\w*\s+ліні\w*)")
_HOTLINE_FUTURE = _rx(r"(?:відбудеться|у\s+понеділок|у\s+вівторок|"
                     r"о\s+\d{1,2}[.:]\d{2}\s+годин\w*)")
_RITUAL_GREETING = _rx(r"(?:щиро\s+вітаю\s+вас\s+із\s+днем|"
                      r"щиро\s+вітаємо\s+(?:вас\s+)?(?:з|із)\s+днем|"
                      r"шановні\s+працівники.{0,150}\bвітаю\b|"
                      r"хліб,?\s+здобутий\s+крізь\s+вогонь)")
_HEALTH_EDUCATION_HEAD = _rx(r"(?:всесвітн\w*\s+день\s+боротьби\s+з\s+діабетом\b|"
                            r"для\s+дорослих,?\s+які\s+хочуть\s+кинути\s+курити|"
                            r"немає\s+диму\s*[-—]\s*не\s+означає|"
                            r"місце\s+для\s+кожного:\s*як\s+організувати\s+простір|"
                            r"чому\s+люди,?\s+які\s+[«\"]?хочуть\s+знайти)")
_NONLOCAL_HEAD = _rx(r"(?:\bнорвегі\w*\b.{0,65}\b(?:спортсмен\w*|в.?їзд)|"
                    r"\bіспані\w*\b.{0,90}\b(?:родин\w*|підтрим\w*\s+україн\w*)|"
                    r"\bпавлоград\w*\b|\bдніпропетровщин\w*\b|"
                    r"\bпонад\s+80\s*%\s+українськ\w*\s+медик\w*|"
                    r"\bросі\w*\s+відмовил\w*\s+від\s+енергетичн\w*\s+перемир|"
                    r"\bпереговор\w*\s+(?:в\s+|із\s+)?(?:росі|зеленськ))")
_ORIGINAL_LOCAL_EVENT = _rx(r"\b(?:запоріж\w*|запоріз\w*|мелітопол\w*|"
                           r"бердянськ\w*|енергодар\w*|оріхів\w*|"
                           r"полог\w*|гуляйпол\w*|токмак\w*|"
                           r"василів\w*|дніпрорудн\w*)\b")
_NONGROUNDED_ACCIDENT = _rx(r"\bдтп\s+на\s+україн[іи]\b")
_RANT_HEAD = _rx(r"(?:\bвчора\s+аналогічно\s+вчинили\b|"
                r"люди,?\s+які\s+займаються\s+чергами\s+та\s+плануванням)")

# A substantive scientific result is not an app/device walkthrough. Excluding
# a simulator *tutorial* must not forbid an original robot simulator model.
_SCIENCE_WALKTHROUGH_HEAD = _rx(r"(?:\bbuild\s+a\s+robot\s+pick[- ]and[- ]place\s+simulation|"
                              r"\b(?:how\s+to|guide\s+to)\s+(?:build|run|make)\s+"
                              r"(?:a\s+)?(?:robot|simulation|nvidia\s+isaac))")
_SIMULATOR_WALKTHROUGH_BODY = _rx(r"(?:\bwalkthrough\b|"
                                 r"step[- ]by[- ]step|"
                                 r"compose\s+a\s+scene.*run\s+a\s+pick[- ]and[- ]place)")
_PODCAST_EPISODE_HEAD = _rx(r"\bpodcast\s*:\s*episode\s+\d+\b")
_GPU_CONSUMER_ADVICE_HEAD = _rx(r"(?:here['’]?s\s+when\s+a\s+dedicated\s+graphics\s+card\s+is\s+worth\s+it|"
                               r"when\s+(?:is|should).{0,70}(?:buy|need).{0,30}(?:gpu|graphics\s+card))")

# Consumer lists are rejected for the absence of any original maker/event,
# not on numeric titles or list format alone. This must preserve art lists,
# original cabin design collections, named design objects and real innovation.
_EMPTY_RESTAURANT_RANKING = _rx(r"(?:\bbest\s+(?:fried\s+)?fish\s+joint\s+in\s+every\s+state\b|"
                               r"\bbest\s+(?:restaurants?|diners?|food\s+spots?)\s+in\s+(?:every|all\s+50)\s+state)")
_GROCERY_VS_REVIEW = _rx(r"\b(?:walmart(?:['’]s)?\s+great\s+value|costco|trader\s+joe['’]?s|ocean\s+spray)\b"
                        r".{0,100}\b(?:vs\.?|versus)\b.{0,100}"
                        r"\b(?:walmart|costco|trader\s+joe|ocean\s+spray)\b")
_CONSUMER_FOOD_REVIEW = _rx(r"\b(?:cranberry\s+sauce|shredded\s+rotisserie\s+chicken|"
                            r"grocery\s+products?|food\s+review|taste\s+test)\b")
_REFERENCE_EXPLAINER = _rx(r"\bwhat\s+do\s+all\s+the\s+flags\s+mean\s+in\s+racing\b")
_PURE_COLORWAY_TITLE = _rx(r"\b(?:holiday\s+toast\s+trackers?\s+bring\s+cranberry|"
                          r"(?:new|holiday|seasonal)\s+(?:colors?|colourways?|shades?)\b|"
                          r"\bin\s+(?:three|two|\d+)\s+.{0,40}\bcolorways?\b|"
                          r"(?:comes?|arrives?|available|drops?)\s+in\s+(?:new|two|three|fresh)\s+(?:colors?|colours?|shades?))")
_PURE_COLORWAY_BODY = _rx(r"\b(?:colorways?|colourways?|colors?|colours?|shades?)\b")
_AUDI_EXPORT_RUMOR = _rx(r"\b(?:next[- ]gen\s+)?audi\s+rs6\s+avant\s+(?:coming|heading)\s+to\s+(?:the\s+)?u\.?s\.?")

# Final text is an independent artifact. Never invent a missing link or allow
# dangling 'за посиланням:' instructions to Telegram. A real linked URL keeps
# the editorial source/final guard happy; unrelated footer link is not proof.
_BROKEN_LINK_PHRASE = _rx(r"(?:за\s+посиланням\s*:\s*(?:або\b|[.!?;,]|$|\n)|"
                         r"(?:на\s+сайті|за\s+адресою|докладніше\s+тут)[^\n:.]{0,65}:\s*(?:\n|$))")
_URL = _rx(r"https?://[^\s<>()]+")


def monitoring_source_reason_2332(article: Any) -> str:
    """Return only evidence-based source vetoes for the Zaporizhzhia channel."""
    title = _v(article, "title")[:1300]
    raw = _v(article, "raw_text")[:16000]
    if not title and not raw:
        return ""
    # Title is often the full stitched Telegram message. Cap fragments to
    # avoid a publisher promo/footer falsely turning a real recap into alert.
    paragraphs = re.split(r"(?<=[.!?])\s*|(?=[🚧✈🚀])", (raw or title)[:1500])
    for part in paragraphs:
        snippet = _SOURCE_PROMO.sub("", part).strip()
        if len(snippet) <= 185 and _TACTICAL_WEAPON.search(snippet) and _TACTICAL_DESTINATION.search(snippet) and not _TACTICAL_SETTLED.search(snippet):
            return "MONITORING_ACTIVE_AERIAL_ROUTE_2332"
    lead = (title or raw)[:570]
    source = (raw or title)[:8500]
    if _DONATION_ASK.search(source) and _FUNDRAISE_CONTEXT.search(source):
        return "MONITORING_FUNDRAISING_APPEAL_2332"
    if _FAREWELL_NOTICE.search(lead):
        return "MONITORING_FUTURE_FUNERAL_NOTICE_2332"
    if _HOTLINE_NOTICE.search(lead) and _HOTLINE_FUTURE.search(source[:900]):
        return "MONITORING_HOTLINE_INVITATION_2332"
    if _RITUAL_GREETING.search(lead):
        return "MONITORING_RITUAL_GREETING_2332"
    if _HEALTH_EDUCATION_HEAD.search(lead):
        return "MONITORING_GENERIC_ADVICE_NOT_NEWS_2332"
    # Explicitly remote/national *subject* without any original Zaporizhzhia
    # event. Do not infer regional relevance from the submitting feed's name.
    if _NONLOCAL_HEAD.search(lead) and not _ORIGINAL_LOCAL_EVENT.search(source[:2600]):
        return "MONITORING_NONLOCAL_SUBJECT_2332"
    if _NONGROUNDED_ACCIDENT.search(lead) and not _ORIGINAL_LOCAL_EVENT.search(source[:650]):
        return "MONITORING_ACCIDENT_LOCATION_AMBIGUOUS_2332"
    if _RANT_HEAD.search(lead):
        return "MONITORING_UNVERIFIED_READER_RANT_2332"
    return ""


def editorial_source_reason_2332(role: str, article: Any) -> str:
    """Conservative science/creative topic veto with positive source proof."""
    if role not in {"science", "creative"}:
        return ""
    title = _v(article, "title")[:1600]
    body = _v(article, "raw_text")[:14000]
    if not title or not body:
        return ""
    if role == "science":
        if _SCIENCE_WALKTHROUGH_HEAD.search(title) and _SIMULATOR_WALKTHROUGH_BODY.search(body[:4500]):
            return "SCIENCE_SIMULATOR_TUTORIAL_NOT_NEWS_2332"
        if _PODCAST_EPISODE_HEAD.search(title):
            return "SCIENCE_PODCAST_EPISODE_PROMO_2332"
        if _GPU_CONSUMER_ADVICE_HEAD.search(title):
            return "SCIENCE_GPU_BUYER_TIPS_2332"
        return ""
    if _EMPTY_RESTAURANT_RANKING.search(title):
        return "CREATIVE_GENERIC_RESTAURANT_RANKING_2332"
    if _GROCERY_VS_REVIEW.search(title) and _CONSUMER_FOOD_REVIEW.search(title + " " + body[:600]):
        return "CREATIVE_ROUTINE_GROCERY_COMPARISON_2332"
    if _REFERENCE_EXPLAINER.search(title):
        return "CREATIVE_REFERENCE_TUTORIAL_2332"
    if _AUDI_EXPORT_RUMOR.search(title):
        return "CREATIVE_ROUTINE_EXPORT_RUMOR_2332"
    if _PURE_COLORWAY_TITLE.search(title) and _PURE_COLORWAY_BODY.search(body[:2000]):
        return "CREATIVE_COLORWAY_ONLY_2332"
    return ""


def final_artifact_reason_2332(article: Any, text: str) -> str:
    """Final text guard; no changes to original source URLs or Telegram footer."""
    if not text:
        return ""
    if _BROKEN_LINK_PHRASE.search(text):
        return "FINAL_BROKEN_OR_MISSING_LINK_2332"
    # A source-local street/locality must not be rewritten as country-wide
    # fact; we do not guess the municipality from a regional feed's name.
    source = (_v(article, "title") + "\n" + _v(article, "raw_text"))[:1500]
    if (_NONGROUNDED_ACCIDENT.search(source)
            and re.search(r"(?iu)\bв\s+україн[іи]\s+стал\w*\s+дтп", text)
            and not _ORIGINAL_LOCAL_EVENT.search(source)):
        return "FINAL_UNGROUNDED_ACCIDENT_LOCATION_2332"
    return ""