"""Conservative final-stage published-incident dedupe for short local news rewrites.

Only block thin Zaporizhzhia strike injury summaries within a 20-minute
window of a previously committed injury/strike post. Full official updates
with additional distinct facts are not reclassified as duplicates by this
guard; the normal detailed event dedupe still applies.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta


def _is_strike_injury(text: str) -> bool:
    low = str(text or "").casefold()
    return bool(
        re.search(r"поран|постраждал|загин|загибл|вбит", low)
        and re.search(r"удар|атак|обстріл|ракет|дрон|каб", low)
    )


def _region(text: str) -> str:
    low = str(text or "").casefold()
    if "запорі" in low:
        return "zaporizhzhia"
    return ""



_FATAL_NUMBER_WORDS = {
    "один": 1, "одна": 1, "одну": 1, "однієї": 1,
    "двоє": 2, "дві": 2, "два": 2, "двох": 2,
    "троє": 3, "три": 3, "трьох": 3,
    "четверо": 4, "чотири": 4, "чотирьох": 4,
    "п'ятеро": 5, "п’ятеро": 5, "п'ять": 5, "п’ять": 5,
}
_FATAL_NUMBER_PATTERN = (
    r"(?:\d{1,3}|" + "|".join(re.escape(k) for k in _FATAL_NUMBER_WORDS) + r")"
)
_FATAL_CONTEXT = re.compile(
    r"(?iu)\b(?:загин\w*|загибл\w*|вбит\w*)\b"
    r"[^.!?\n]{0,65}?\b(" + _FATAL_NUMBER_PATTERN + r")\b|"
    r"\b(" + _FATAL_NUMBER_PATTERN + r")\b"
    r"[^.!?\n]{0,40}\b(?:загин\w*|загибл\w*|вбит\w*)\b"
)
_PRIVATE_RESIDENTIAL = re.compile(
    r"(?iu)\bприватн\w*\s+(?:житлов\w*\s+)?(?:будин\w*|сектор\w*|осел\w*)\b"
)
_NAMED_SITE = re.compile(
    r"(?iu)\b(?:вул(?:иц[яі])?\.?|провул(?:ок|ку)|просп(?:ект|екті)?\.?)\s+"
    r"([а-яіїєґ][а-яіїєґ'-]{3,})"
)
_CONFIRMED_UPDATE = re.compile(
    r"(?iu)\b(?:оновлен\w*|уточнен\w*|кількість\s+загибл\w*\s+зросл\w*|"
    r"нові\s+підтверджен\w*\s+(?:наслідк\w*|детал\w*))\b"
)


def _fatal_count(text: str) -> int | None:
    match = _FATAL_CONTEXT.search(str(text or ""))
    if match is None:
        return None
    token = str(match.group(1) or match.group(2) or "").casefold()
    if token.isdigit():
        return int(token)
    return _FATAL_NUMBER_WORDS.get(token)


def _same_short_fatal_residential_event(current: str, prior: str) -> bool:
    """Strict same-area, same-fatality, same-target, short-interval replay guard.

    Compare two source-owned summaries, not language-model rewrites. A changed
    casualty count, different named street or explicit follow-up is a new update
    and must be allowed. Publisher checks <=20 minutes from an actual delivery.
    """
    left_count, right_count = _fatal_count(current), _fatal_count(prior)
    if left_count is None or right_count is None or left_count != right_count:
        return False
    if not (_PRIVATE_RESIDENTIAL.search(current) and _PRIVATE_RESIDENTIAL.search(prior)):
        return False
    if _region(current) != _region(prior) or not _region(current):
        return False
    if not (_is_strike_injury(current) and _is_strike_injury(prior)):
        return False
    left_sites = set(_NAMED_SITE.findall(current))
    right_sites = set(_NAMED_SITE.findall(prior))
    if left_sites and right_sites and left_sites.isdisjoint(right_sites):
        return False
    if _CONFIRMED_UPDATE.search(current):
        return False
    return True


def recent_community_incident_duplicate(store, channel_id: int, article_id: int, article) -> int:
    if int(channel_id) != 3:
        return 0
    source_text = str(article["raw_text"] or "")
    final_text = str(article["final_text"] or "")
    title = str(article["title"] or "")
    if not _is_strike_injury(" ".join((source_text, title, final_text))):
        return 0
    # Thin rephrased headline-only stories are not a fresh incident update.
    # Longer Telegram captions sometimes append bot links or newsroom footers.
    # Fatal private-house briefs are matched from original facts instead of an
    # arbitrary caption length; distinct updates still remain publishable.
    original = " ".join((title, source_text))
    if len(source_text.strip()) > 175 and not (
        _fatal_count(original) is not None and _PRIVATE_RESIDENTIAL.search(original)
    ):
        return 0
    try:
        published = []
        with store.connect() as con:
            published = con.execute(
                """SELECT article_id, title, raw_text, final_text, published_at
                   FROM published_event_ledger
                   WHERE channel_id=? AND article_id<>?
                   ORDER BY published_at DESC LIMIT 60""",
                (channel_id, article_id),
            ).fetchall()
        now = datetime.now().astimezone()
        current_region = _region(" ".join((title, source_text, final_text)))
        if not current_region:
            return 0
        for item in published:
            other_at = datetime.fromisoformat(str(item["published_at"]).replace("Z", "+00:00"))
            if not other_at.tzinfo:
                continue
            if not timedelta(0) <= (now - other_at.astimezone(now.tzinfo)) <= timedelta(minutes=20):
                continue
            other = " ".join((str(item["title"] or ""), str(item["raw_text"] or ""), str(item["final_text"] or "")))
            if not _is_strike_injury(other) or _region(other) != current_region:
                continue
            # For fatal residential strikes, a same-event assertion needs
            # matching source-owned casualty count and same private dwelling
            # context; generic "strike in Zaporizhzhia" is not enough.
            prior_original = " ".join((str(item["title"] or ""), str(item["raw_text"] or "")))
            if _fatal_count(original) is not None or _fatal_count(prior_original) is not None:
                if not _same_short_fatal_residential_event(original, prior_original):
                    continue
            return int(item["article_id"])
    except (ValueError, TypeError, KeyError):
        return 0
    return 0
