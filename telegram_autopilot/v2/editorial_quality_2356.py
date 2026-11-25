"""Owner-reviewed 2.3.56 editorial quality, grounded in ORIGINAL source.

This module does not score an entire category, block a brand, fetch pages or
invent a media caption. Only high-precision combinations from the source are
hard vetoes. The pre-AI/source check is repeated for carried-over READY posts.
"""
from __future__ import annotations

import re
from typing import Any


def _read(row: Any, key: str) -> str:
    try:
        value = row[key]
    except (KeyError, IndexError, TypeError):
        value = getattr(row, key, "")
    return str(value or "")


_RETAIL_FLAVOR_TITLE = re.compile(
    r"(?iu)(?:(?:new|returning|back|seasonal|holiday|limited[- ]time|"
    r"flavou?r|just\s+(?:dropped|launched|arrived))\b[^\n.!?]{0,100}"
    r"\b(?:cookies?|biscuits?|snacks?|crackers?|desserts?|sweets?|candy|"
    r"shortbread|ice\s*cream|treats?|chips?)\b|"
    r"\b(?:cookies?|biscuits?|snacks?|crackers?|desserts?|sweets?|"
    r"shortbread|treats?)\b[^\n.!?]{0,100}\b(?:new|returning|back|"
    r"seasonal|holiday|limited[- ]time|flavou?r)\b)"
)
_RETAIL_CUES = (
    re.compile(r"(?iu)(?:\$\s*\d+|\b(?:price|priced|costs?|\d\s*(?:oz|ounce|grams?|g))\b)"),
    re.compile(r"(?iu)\b(?:available|in\s+(?:stores?|stock)|on\s+shelves|"
               r"limited[- ]time|seasonal|holiday|this\s+month)\b"),
    re.compile(r"(?iu)\b(?:shoppers?|customers?|fans?|reviewers?)\b[^.!?]{0,100}"
               r"\b(?:say|said|love|think|rated|review|taste|flavou?r)\b"),
    re.compile(r"(?iu)\b(?:buy|purchase|pick\s+up|shop|cart|"
               r"try\s+(?:the|these)|tastes?\s+like|flavou?r\s+notes?)\b"),
)
# A documented unusual creation is not a routine flavor announcement.
# These phrases cannot rescue unrelated retail fluff in the article body;
# at least one must describe the TOPIC in the source title/lead.
_CREATIVE_TOPIC = re.compile(
    r"(?iu)\b(?:3d[- ]print\w*|sculptur\w*|interactive|kinetic|"
    r"mechanical|engineer\w*|prototype|artwork|redesign\w*|"
    r"installation|architecture|upcycl\w*|robot\w*|"
    r"gameplay|augmented\s+reality|invent\w*|"
    r"інтерактивн\w*|інженерн\w*|нов\w*\s+механізм)\b"
)

_SCHOOL_RECAP_TITLE = re.compile(
    r"(?iu)\b(?:тиждень|підсумки\s+тижня)\b[^.!?\n]{0,90}"
    r"\b(?:початков\w*\s+школ\w*|початков\w*\s+освіт\w*)\b"
)
_SCHOOL_INTERNAL = re.compile(r"(?iu)\b(?:урок\w*|квест\w*|вікторин\w*|"
                              r"майстер[- ]клас\w*|гра\w*|конкурс\w*|"
                              r"малювал\w*|учн\w*)\b")
_SCHOOL_PUBLIC_RESULT = re.compile(
    r"(?iu)\b(?:відкрили|відновили|запрацювал\w*|облаштувал\w*|"
    r"укритт\w*|розпочал\w*\s+навчанн\w*|кошти\s+для|"
    r"зібрал\w*\s+\d+|передал\w*\s+допомог\w*|"
    r"підтримк\w*\s+(?:дітей|родин)|нагород\w*|"
    r"реабілітаці\w*|безпек\w*|інклюзивн\w*)\b"
)
_LOCAL_TAX_BENEFIT = re.compile(
    r"(?iu)\b(?:бюджет\w*\s+(?:запоріз\w*\s+)?(?:громад\w*|міст\w*|"
    r"сіл\w*|селищ\w*)|місцев\w*\s+бюджет\w*\s+"
    r"(?:отрим\w*|надійш\w*)|спрямувал\w*\s+на\s+"
    r"(?:школ\w*|лікарн\w*|ремонт\w*|укритт\w*|підтримк\w*)|"
    r"фінансуванн\w*\s+(?:конкретн\w*|проект\w*|проєкт\w*))\b"
)


def creative_routine_product_reason_2356(article: Any) -> str:
    """Narrow routine retail food launch, not a ban on food or products."""
    title = _read(article, "title")[:600]
    source = _read(article, "raw_text")[:8500]
    if not (title and source and _RETAIL_FLAVOR_TITLE.search(title)):
        return ""
    if _CREATIVE_TOPIC.search(title + " " + source[:360]):
        return ""
    cues = sum(bool(p.search(source)) for p in _RETAIL_CUES)
    if cues < 2:
        return ""  # insufficient evidence of mere shelf/price promotion
    return "CREATIVE_ORDINARY_SEASONAL_PRODUCT_2356"


def regional_non_news_reason_2356(article: Any) -> str:
    """Veto only a verified internal school-week recap with no public result.

    Tax revenue can matter even when reported by a private company. Do not
    automatically reject tax reports as PR: the value gate must assess the
    VERIFIED local budget/beneficiary and freshness, not the publisher brand.
    """
    title = _read(article, "title")[:600]
    raw = _read(article, "raw_text")[:8500]
    if (_SCHOOL_RECAP_TITLE.search(title) and _SCHOOL_INTERNAL.search(raw)
            and not _SCHOOL_PUBLIC_RESULT.search(raw)):
        return "MONITORING_INTERNAL_SCHOOL_WEEK_NO_PUBLIC_RESULT_2356"
    # Company-wide retrospective totals, when they contain NO source-owned
    # local budget outcome, are corporate publicity rather than a new civic
    # change. No brand bans. Local tax/budget consequences remain eligible.
    combined = title + "\n" + raw
    if (re.search(r"(?iu)\b(?:податк\w*|податков\w*\s+надходжен\w*)\b", title)
            and re.search(r"(?iu)\b(?:підприємств\w*|компані\w*|груп\w*|"
                          r"металургійн\w*|бізнес\w*)\b", combined)
            and re.search(r"(?iu)\b(?:сплатил\w*|перерахувал\w*|сплачено|"
                          r"відрахуван\w*)\b", combined)
            and re.search(r"(?iu)\b(?:за\s+\d+\s+місяц\w*|з\s+початку\s+року|"
                          r"за\s+(?:цей|минулий|поточний)\s+рік|підсумк\w*\s+року)\b", combined)
            and not _LOCAL_TAX_BENEFIT.search(combined)):
        return "MONITORING_CORPORATE_AGGREGATE_WITHOUT_LOCAL_RESULT_2356"
    return ""


_SHARED_BROWSER = re.compile(
    r"(?iu)(?:\b(?:shared?|multiplayer|co[- ]?browse|together)\b[^.!?\n]{0,100}"
    r"\b(?:browser|websites?|web\s+pages?|internet)\b|"
    r"\b(?:browser|websites?|web\s+pages?)\b[^.!?\n]{0,100}"
    r"\b(?:shared?|multiplayer|together)\b|"
    r"спільн\w*\s+браузер\w*|разом\s+перегляда\w*\s+сайт\w*)"
)
_FISHING = re.compile(r"(?iu)\b(?:fishing|fish\s+on|go\s+fishing|"
                      r"рибал\w*|вудк\w*|лов\w*\s+риб\w*)\b")
_BROWSER = re.compile(r"(?iu)\b(?:browser|website\w*|web\s*page\w*|"
                      r"webpage\w*|сайт\w*|вебсторін\w*|браузер\w*)\b")


def source_browser_fishing_mechanic_2356(article: Any) -> bool:
    """Source explicitly ties together shared browser + fishing game.

    This identifies the INTERACTION to explain, *not* the attached media.
    The screenshot must be independently verified before describing pixels.
    """
    raw = _read(article, "raw_text")[:8000]
    title = _read(article, "title")[:500]
    all_source = title + "\n" + raw
    return bool(_FISHING.search(all_source) and _BROWSER.search(all_source)
                and _SHARED_BROWSER.search(all_source))


_BRIDGE_ACTION = re.compile(r"(?iu)\b(?:рибал\w*|вудк\w*|лов\w*\s+риб\w*)\b")
_BRIDGE_PLACE = re.compile(r"(?iu)(?:\b(?:поверх|просто\s+на|безпосередньо\s+на)\b"
                           r"[^.!?\n]{0,85}\b(?:сайт\w*|вебсторін\w*|"
                           r"сторін\w*|відео|ролик\w*|браузер\w*|ютуб\w*|YouTube)\b|"
                           r"\b(?:на\s+(?:будь[- ]як\w*\s+)?(?:сайт\w*|"
                           r"вебсторін\w*))\b)")


def missing_visual_story_bridge_2356(article: Any, candidate: str, *, commercial: bool) -> str:
    """No feature-list caption for evidence-backed browser-overlay games.

    The first 390 characters must convey the interaction. Does NOT claim a
    particular screenshot was selected, and does NOT require every post to
    narrate a picture or add a separate AI call.
    """
    if not commercial or not source_browser_fishing_mechanic_2356(article):
        return ""
    opening = str(candidate or "")[:390]
    if _BRIDGE_ACTION.search(opening) and _BRIDGE_PLACE.search(opening):
        return ""
    return "CREATIVE_VISUAL_MECHANIC_UNEXPLAINED_2356"


def visual_story_prompt_2356(article: Any, *, commercial: bool) -> str:
    if not commercial or not source_browser_fishing_mechanic_2356(article):
        return ""
    return (
        "\nКРИТИЧНА ЯСНІСТЬ ВІЗУАЛЬНОЇ МЕХАНІКИ 2.3.56: SOURCE описує "
        "спільний браузер та риболовлю. Поясни у ПЕРШИХ 1–3 реченнях, "
        "що саме гравці роблять на/поверх відкритої вебсторінки, а не "
        "просто перераховуй мініігри. Читач без знання гри має зрозуміти "
        "поєднання сайту й риболовлі. Не стверджуй, що КОНКРЕТНИЙ "
        "прикріплений кадр містить щось, чого ти не перевіряв. "
        "Усі твердження лише за SOURCE."
    )


REGIONAL_NEWS_VALUE_PROMPT_2356 = (
    "\nРЕГІОНАЛЬНА РЕДАКЦІЙНА ПЕРЕВІРКА 2.3.56: наявність 500 символів "
    "НЕ робить матеріал новиною. Розрізняй звіт установи про внутрішній "
    "тиждень активностей, загальний корпоративний PR і підтверджену "
    "нову суспільно значущу зміну. Для податків не відхиляй сам факт "
    "корпоративного походження: перевір, чи SOURCE дає актуальну конкретну "
    "користь для бюджету громади, суму/одержувача або інший локальний "
    "наслідок. Не вигадуй результат або бюджетну прив'язку. "
    "Не блокуй реальну допомогу, послуги, рішення, ремонти, безпеку, "
    "евакуацію й доступні мешканцям зміни."
)


__all__ = [
    "creative_routine_product_reason_2356", "regional_non_news_reason_2356",
    "source_browser_fishing_mechanic_2356", "missing_visual_story_bridge_2356",
    "visual_story_prompt_2356", "REGIONAL_NEWS_VALUE_PROMPT_2356",
]
