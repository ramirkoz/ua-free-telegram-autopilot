"""2.3.12: source-only protection for three actually published civic false positives.

Never use the local publisher's NAME/URL to infer regional source content.
These narrowly scoped gates do not replace the main civic inclusion policy.
"""
from __future__ import annotations

import re
from typing import Any

from .live_editorial_integrity_239 import _field, _LOCAL


_URL = re.compile(r"https?://\S+", re.I)
_NATIONAL_NETWORK = re.compile(
    r"(?iu)антимобілізаційн\w*|анти\s*мобілізаційн\w*|"
    r"мереж\w*\s+вплив\w*|інформаційн\w*\s+мереж\w*"
)
_SOCIAL_CAMPAIGN = re.compile(
    r"(?iu)\b(?:блогер\w*|інфлюенсер\w*|підписник\w*|"
    r"проросійськ\w*\s+ресурс\w*|соцмереж\w*)\b"
)
_NETWORK_MEASURE = re.compile(
    r"(?iu)\b(?:мільйон\w*|млн\b|мереж\w*|"
    r"розслідуванн\w*|підписник\w*)\b"
)
_KILLING = re.compile(
    r"(?iu)\b(?:застрелив\w*|розстріляв\w*|"
    r"убив\w*|вбив\w*|контрольн\w*\s+постріл\w*)\b"
)
_INTERNAL_MILITARY = re.compile(
    r"(?iu)\b(?:офіцер\w*|капітан\w*|командир\w*|"
    r"танкіст\w*|військовослужбовц\w*|солдат\w*)\b"
)
_CREDIBLE_CONFIRMATION = re.compile(
    r"(?iu)\b(?:поліці\w*|ГУР|СБУ|генштаб\w*|прокуратур\w*|"
    r"офіційн\w*\s+відомств\w*)\b[^.!?\n]{0,110}"
    r"\b(?:підтвердил\w*|повідомил\w*|оприлюднил\w*)\b"
    r"|(?:підтвердил\w*|повідомил\w*)\b[^.!?\n]{0,80}"
    r"\b(?:поліці\w*|ГУР|СБУ|генштаб\w*|прокуратур\w*)\b"
)
_ANON_VETERAN_OPINION = re.compile(
    r"(?iu)\b(?:заяв\w*\s+ветеран\w*|"
    r"ветеран\w*\s+(?:засудив\w*|обурив\w*|"
    r"звернув\w*\s+увагу|розкритикував\w*))\b"
)
_EMOTIVE_OPINION = re.compile(
    r"(?iu)\b(?:нахабств\w*|патяка\w*|сором\w*|"
    r"антиукраїнськ\w*\s+вкид\w*|"
    r"критичн\w*\s+мисленн\w*)\b"
)
_NAMED_SPEAKER = re.compile(
    r"(?u)\b[А-ЯІЇЄҐ][а-яіїєґ'’\-]{2,}\s+"
    r"[А-ЯІЇЄҐ][а-яіїєґ'’\-]{2,}\b"
)


def _source_only(article: Any) -> str:
    raw = _URL.sub(" ", _field(article, "raw_text"))
    # The Telegram publisher's branding is never local event evidence.
    # Strip social invites after the first self-promotional call to action.
    raw = re.split(r"(?iu)\bми\s+в\s*[📱📲]", raw, maxsplit=1)[0]
    title = _URL.sub(" ", _field(article, "title"))
    return (title + "\n" + raw).strip()


def monitoring_editorial_integrity_2312(article: Any) -> str:
    source = _source_only(article)
    if not source:
        return ""
    # #90710: nationwide social-media investigation copied by local feed.
    # Explicit Zaporizhzhia facts preserve genuinely local investigations.
    if (not _LOCAL.search(source)
            and _NATIONAL_NETWORK.search(source)
            and _SOCIAL_CAMPAIGN.search(source)
            and _NETWORK_MEASURE.search(source)):
        return "MONITORING_NATIONAL_ONLY_NETWORK_ANALYSIS_2312"
    # #90809: anonymous Telegram account alleging an officer murdered two
    # soldiers, named unit & exact circumstances, no official confirmation.
    # Local geography alone cannot turn this accusation into verified fact.
    if (_KILLING.search(source) and _INTERNAL_MILITARY.search(source)
            and not _CREDIBLE_CONFIRMATION.search(source)):
        return "MONITORING_UNVERIFIED_INTERNAL_KILLING_2312"
    # #90845: anonymous emotional anti-opinion framed as a concrete veteran
    # announcement. A named person or a genuine local event stays eligible.
    if (not _LOCAL.search(source)
            and _ANON_VETERAN_OPINION.search(source)
            and _EMOTIVE_OPINION.search(source)
            and not _NAMED_SPEAKER.search(source)):
        return "MONITORING_UNATTRIBUTED_OPINION_2312"
    return ""
