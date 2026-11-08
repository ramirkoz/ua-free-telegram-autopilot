"""2.3.17: conservative source-only regional editorial exclusions.

The original source text, not the publisher name or generated rewrite, must
establish regional relevance.  Applied only to monitoring channels with the
existing LIVE_NOW_RC96 opt-in; independent Fact/Media/Telegram guards remain.
"""
from __future__ import annotations

import re
from typing import Any

from .domain import ChannelMode


def _field(row: Any, key: str) -> str:
    try:
        value = row[key]
    except (KeyError, TypeError, IndexError):
        value = getattr(row, key, "")
    return str(value or "")


_LOCAL_EVENT = re.compile(
    r"(?iu)\b(?:запоріж\w*|запоріз\w*|мелітопол\w*|бердянськ\w*|"
    r"енергодар\w*|токмак\w*|гуляйпол\w*|оріхів\w*|"
    r"василів\w*|полог\w*|дніпрорудн\w*)\b"
)
# Concrete nature stories from distant geography do not become local news
# merely because a Zaporizhzhia Telegram channel republishes them.
_REMOTE_NATURE_PLACE = re.compile(
    r"(?iu)\b(?:антарктид\w*|антарктичн\w*|гал[ао]пагос\w*|"
    r"арктичн\w*|амазонськ\w*\s+(?:ліс\w*|джунгл\w*))\b"
)
_REMOTE_NATURE_EVENT = re.compile(
    r"(?iu)\b(?:пінгвін\w*|птах\w*|яйц\w*|яєць|гнізд\w*|"
    r"колоні\w*|тварин\w*|популяці\w*|"
    r"біолог\w*|природ\w*|станці\w*\s*[«„\"]?вернадськ\w*)\b"
)

# 2.3.18: a local publisher's unrelated weather clip from other regions
# is not a Zaporizhzhia event. Require named remote geography + weather
# AND absence of an original-source Zaporizhzhia connection; generic national
# laws, national aid and weather genuinely reported for the region remain eligible.
_REMOTE_WEATHER_PLACE_2318 = re.compile(
    r"(?iu)\b(?:львівщин\w*|львівськ\w*\s+област\w*|"
    r"івано[- ]франківщин\w*|івано[- ]франківськ\w*\s+област\w*|"
    r"черкащин\w*|черкаськ\w*\s+област\w*|"
    r"закарпат\w*|волин\w*|прикарпат\w*)\b"
)
_REMOTE_WEATHER_EVENT_2318 = re.compile(
    r"(?iu)\b(?:сніг\w*|сніж\w*|дощ\w*|злив\w*|"
    r"заморозк\w*|ожелед\w*|хуртовин\w*|мороз\w*)\b"
)

# 2.3.19: source-only exclusions from 08 Nov published editorial audit.
# Do not treat a publisher's own location or generic repost footer as a
# connection of an overseas/distant event to Zaporizhzhia.
_TRIVIAL_SOCIAL_GREETING_2319 = re.compile(
    r"(?iu)(?:маєте\s+ідеї\s+до\s+обіду|всім\s+смачного|"
    r"смачного\s+обіду|що\s+сьогодні\s+на\s+обід|"
    r"побажаємо\s+(?:гарного\s+дня|смачного))"
)
_CONCRETE_CIVIC_EVENT_2319 = re.compile(
    r"(?iu)\b(?:відкрили|відкриють|відбудеться|відбулася|стартував|"
    r"запрацював|організували|розпочинається|оголосили\s+(?:набір|конкурс)|"
    r"безкоштовн\w*\s+(?:занятт\w*|послуг\w*|захід))\b"
)
_REMOTE_DIPLOMACY_2319 = re.compile(
    r"(?iu)\b(?:абу[- ]дабі|об’єднан\w*\s+арабськ\w*\s+емірат\w*)\b"
)
_DIPLOMATIC_EVENT_2319 = re.compile(
    r"(?iu)\b(?:переговор\w*|дипломат\w*|саміт\w*|зустріч\w*\s+делегац\w*)\b"
)
_REMOTE_CHERKASY_2319 = re.compile(r"(?iu)\b(?:черкащин\w*|черкаськ\w*\s+област\w*)\b")
_REMOTE_TRAGEDY_2319 = re.compile(
    r"(?iu)\b(?:військов\w*|медик\w*|загиб\w*|трагеді\w*|злочин\w*)\b"
)
_CENTRAL_ASIA_2319 = re.compile(
    r"(?iu)\b(?:центральн\w*\s+азі\w*|таджикистан\w*|узбекистан\w*|"
    r"киргизстан\w*|казахстан\w*)\b"
)
_CENTRAL_ASIA_RECRUITMENT_2319 = re.compile(
    r"(?iu)\b(?:вербуван\w*|рекрут\w*|найманц\w*|армі\w*|військ\w*)\b"
)

_RETAIL_CONTEXT = re.compile(
    r"(?iu)\b(?:магазин\w*|супермаркет\w*|гіпермаркет\w*|"
    r"торгов\w*\s+(?:мереж\w*|центр\w*|точк\w*)|"
    r"роздрібн\w*\s+мереж\w*|ритейл\w*)\b"
)
_SALE_OFFER = re.compile(
    r"(?iu)\b(?:знижк\w*|розпродаж\w*|акційн\w*\s+(?:цін\w*|пропозиці\w*)|"
    r"discount\w*|sale\b)\b|\bдо\s*\d{1,2}\s*%"
)
_BUY_NOW = re.compile(
    r"(?iu)\b(?:завітайте|приходьте|купуйте|придбайте|"
    r"поспішайте|встигніть|забирайте|замовляйте|"
    r"тільки\s+(?:сьогодні|завтра)|реклама)\b"
)
_PRICE = re.compile(r"(?iu)\b\d[\d\s\u00a0]{0,8}\s*(?:грн|₴|uah)\b")
_AD_MARK = re.compile(r"(?iu)(?:#реклама\b|\bна\s+правах\s+реклами\b)")
_PUBLIC_BENEFIT = re.compile(
    r"(?iu)\b(?:впо|переселенц\w*|гуманітарн\w*|"
    r"соціальн\w*\s+(?:послуг\w*|допомог\w*)|"
    r"пільгов\w*|субсиді\w*|безоплатн\w*)\b"
)


def monitoring_source_scope_reason_2317(channel: Any, article: Any) -> str:
    """Narrow source veto, idempotent at selection and every send boundary."""
    if getattr(channel, "mode", None) != ChannelMode.MONITORING:
        return ""
    policy = getattr(channel, "policy", None)
    if "[LIVE_NOW_RC96]" not in str(getattr(policy, "rejection_rules", "") or ""):
        return ""
    # Do not use source_name, channel name, link domain, generated final or media.
    original = (_field(article, "title") + "\n" + _field(article, "raw_text"))[:10000]
    if not original.strip():
        return ""

    if (not _LOCAL_EVENT.search(original)
            and _REMOTE_NATURE_PLACE.search(original)
            and _REMOTE_NATURE_EVENT.search(original)):
        return "MONITORING_NONLOCAL_NATURE_2317"

    if (not _LOCAL_EVENT.search(original)
            and _REMOTE_WEATHER_PLACE_2318.search(original)
            and _REMOTE_WEATHER_EVENT_2318.search(original)):
        return "MONITORING_NONLOCAL_UA_WEATHER_2318"

    if (_TRIVIAL_SOCIAL_GREETING_2319.search(original)
            and len(original) <= 650
            and not _CONCRETE_CIVIC_EVENT_2319.search(original)):
        return "MONITORING_SOCIAL_GREETING_NOT_NEWS_2319"

    if not _LOCAL_EVENT.search(original) and not _PUBLIC_BENEFIT.search(original):
        if _REMOTE_DIPLOMACY_2319.search(original) and _DIPLOMATIC_EVENT_2319.search(original):
            return "MONITORING_NONLOCAL_DIPLOMACY_2319"
        if _REMOTE_CHERKASY_2319.search(original) and _REMOTE_TRAGEDY_2319.search(original):
            return "MONITORING_NONLOCAL_CHERKASY_EVENT_2319"
        if _CENTRAL_ASIA_2319.search(original) and _CENTRAL_ASIA_RECRUITMENT_2319.search(original):
            return "MONITORING_NONLOCAL_CENTRAL_ASIA_2319"

    # A neutral, factual opening of a local business is not automatically an ad.
    # A retailer's discount flyer with prices or 'buy now' language is.
    if (_RETAIL_CONTEXT.search(original)
            and _SALE_OFFER.search(original)
            and (_PRICE.search(original) or _BUY_NOW.search(original)
                 or _AD_MARK.search(original))
            and not _PUBLIC_BENEFIT.search(original)):
        return "MONITORING_RETAIL_FLYER_2317"
    return ""
