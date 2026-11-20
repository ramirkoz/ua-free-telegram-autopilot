"""2.3.46 monitoring: a donor's reflective posts are not independent news.

Source-owned, zero-AI-cost editorial guard. A source outlet's sequence of
emotional captions about childhood/war is not a sequence of civic outcomes.
Concrete help, evacuations, legislation and public services remain eligible.
The separate same-source matcher prevents two near-time continuations from
becoming two news items if an older item was already prepared for publishing.
No Telegram token, outgoing draft, feed name or operator-specific blocklist.
"""
from __future__ import annotations

from datetime import datetime
import re
from typing import Any


def _field(row: Any, key: str) -> str:
    try:
        return str(row[key] or "")
    except (KeyError, IndexError, TypeError):
        return str(getattr(row, key, "") or "")


_CHILD = re.compile(r"(?iu)\b(?:дитин\w*|діт\w*|діток|дітки|дітей|малеч\w*)\b")
_REFLECTIVE = (
    re.compile(r"(?iu)\b(?:нехай|хай|бажаємо|побажал\w*|мрі\w*|щаслив\w*|безтурбот\w*)\b"),
    re.compile(r"(?iu)\b(?:мирн\w*\s+неб\w*|обійм\w*|вір\w*\s+в\s+див\w*|дитинство\s+має|діт\w*\s*[—–-]\s*наш\w*\s+майбутн\w*)\b"),
    re.compile(r"(?iu)\b(?:тих\w*\s+бол\w*|не\s+змогл\w*\s+вберегт\w*|війна\s+забрал\w*|війна\s+розкидала|змушен\w*\s+знат\w*|подивіться\s+на\s+них|неймовірн\w*)\b"),
    re.compile(r"(?iu)\b(?:діт\w*\s+заслугову\w*|діт\w*\s+мають\s+прав\w*|ми\s+повинн\w*\s+захист\w*)\b"),
)
_HOLIDAY = re.compile(r"(?iu)\b(?:всесвітн\w*\s+день\s+дитин\w*|день\s+захисту\s+дітей|день\s+дитини)\b")
# Unambiguous completed or scheduled local result; generic nouns such as
# "евакуація" in a list of painful words are NOT proof an evacuation happened.
_CONCRETE = re.compile(
    r"(?iu)\b(?:евакуювал\w*|евакуйован\w*|евакуюють|"
    r"відкрили|відкриють|відкрито|"
    r"запустили|запускають|запровадили|"
    r"організували|організують|провели|проводять|відбувся|відбулася|відбудеться|"
    r"передали|передано|вручили|отримали|отримано|"
    r"затвердили|ухвалили|прийняли\s+рішення|"
    r"розпочали|завершили|відновили|"
    r"постраждал\w*|поранен\w*|загинув|загинула|загинул\w*|загибл\w*|нагородив|нагородила|нагородити|відзначили|"
    r"надають\s+(?:допомогу|послуг\w*)|"
    r"запрошують\s+на\s+(?:зустріч|концерт|поді\w*|заход\w*)|"
    r"реєстрац\w*\s+(?:триває|відкрита|розпочалася)|"
    r"триватиме\s+(?:до|з)|прийом\s+заявок|збір\s+(?:коштів|донат\w*)|реквізит\w*|"
    r"відключ\w*|перекри\w*|графік\w*|розклад\w*|"
    r"інформаці\w*\s+про\s+звернення|"
    r"\d+\s+(?:дітей|дитини|дитин\w*|родин\w*|учн\w*)\s+"
    r"(?:евакуйовано|евакуювали|отримали|пройшли|постраждали))\b"
)


def childhood_reflection_without_event_2346(row: Any) -> str:
    """Reject generic child/war wishes or historical holiday filler, not news.

    Use the immutable source text; avoid generated output and source branding.
    A concrete local civic action/event always takes priority over reflection.
    """
    original = (_field(row, "title") + "\n" + _field(row, "raw_text"))[:14000]
    if len(original.strip()) < 55 or not _CHILD.search(original):
        return ""
    if _CONCRETE.search(original):
        return ""
    if _HOLIDAY.search(original):
        return "MONITORING_CALENDAR_GREETING_NO_CIVIC_EVENT_2346"
    # Only a children-centred wartime reflection, not a real local award,
    # casualty report, career guide or unrelated cultural-holiday message.
    source = _field(row, "raw_text")[:5000]
    childhood_central = bool(_CHILD.search(_field(row, "title"))
                             or _CHILD.search(source[:350]))
    wartime_context = bool(re.search(
        r"(?iu)\b(?:війн\w*|воєнн\w*|сирен\w*|окупаці\w*|укритт\w*)\b", original))
    reflection = sum(bool(pattern.search(original)) for pattern in _REFLECTIVE)
    if childhood_central and wartime_context and reflection >= 1:
        return "MONITORING_CHILDHOOD_REFLECTION_NOT_NEWS_2346"
    return ""


def _timestamp(row: Any) -> float | None:
    for key in ("source_published_at", "published_at", "discovered_at"):
        s = _field(row, key).strip()
        if not s:
            continue
        try:
            value = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if value.tzinfo is not None:
                return value.timestamp()  # normalized across source/ledger
            return value.timestamp()
        except (ValueError, OverflowError):
            continue
    return None


def same_source_reflective_continuation_2346(current: Any, published: Any) -> tuple[bool, str]:
    """Backup for already-READY same-source child-wartime narrative fragments.

    The publication ledger lacks URLs; source_id + original genre + bounded
    timestamps are sufficient *only* for this narrow non-actionable genre.
    Independent updates containing material civic facts are not duplicates.
    """
    a = _field(current, "source_id").strip()
    b = _field(published, "source_id").strip()
    if not a.isdigit() or not b.isdigit() or int(a) <= 0 or a != b:
        return False, ""
    if not childhood_reflection_without_event_2346(current):
        return False, ""
    if not childhood_reflection_without_event_2346(published):
        return False, ""
    t1, t2 = _timestamp(current), _timestamp(published)
    if t1 is None or t2 is None or abs(t1 - t2) > 3 * 3600:
        return False, ""
    return True, "MONITORING_SAME_SOURCE_NON_EVENT_CONTINUATION_2346"


_TELEGRAM_POST = re.compile(r"(?i)^https?://(?:www\.)?t\.me/(?P<name>[a-z0-9_]{3,}|c/\d+)/(?P<post>\d+)(?:[/?#].*)?$")
_THREAD_WORD = re.compile(r"(?iu)[a-zа-яіїєґ]{5,}")
_THREAD_STOP = {"сьогод", "україн", "нашій", "наших", "громад", "запорі", "повідо",
                "сторін", "також", "підчас", "органі", "працю", "людям", "зараз",
                "джерел", "читачі", "новини", "терито", "військ", "російс",
                "цього", "після", "протяг", "через", "переда", "допомо"}
_OPPOSITE_STATUS = (
    (re.compile(r"(?iu)\b(?:перекрил\w*|закрил\w*|зупинил\w*)\b"),
     re.compile(r"(?iu)\b(?:відновил\w*|відкрили|відкрито|відновлено)\b")),
    (re.compile(r"(?iu)\b(?:планують|планується|запланован\w*|очікується)\b"),
     re.compile(r"(?iu)\b(?:завершил\w*|провели|відбулося|відбулася|розпочали)\b")),
)


def _telegram_ref(row: Any) -> tuple[str, int] | None:
    url = _field(row, "canonical_source_url") or _field(row, "source_url")
    match = _TELEGRAM_POST.match(url.strip())
    return (match.group("name").lower(), int(match.group("post"))) if match else None


def _meaningful_stems(row: Any) -> set[str]:
    original = _field(row, "title") + " " + _field(row, "raw_text")[:3500]
    stems = {w[:6] for w in _THREAD_WORD.findall(original.casefold())}
    return {w for w in stems if w not in _THREAD_STOP}


def same_source_telegram_thread_2346(current: Any, prior: Any) -> tuple[bool, str]:
    """Narrow, channel-local confirmation for consecutive Telegram story halves.

    Require 1-2 adjacent original donor messages, near-time, high uncommon
    source-word overlap and no independent new numbers or change of status.
    Different real civic announcements from the same donor remain separate.
    """
    sa, sb = _field(current, "source_id"), _field(prior, "source_id")
    if not sa.isdigit() or int(sa) <= 0 or sa != sb:
        return False, ""
    a, b = _telegram_ref(current), _telegram_ref(prior)
    if not a or not b or a[0] != b[0] or not (0 < abs(a[1] - b[1]) <= 2):
        return False, ""
    at, bt = _timestamp(current), _timestamp(prior)
    if at is None or bt is None or abs(at - bt) > 2 * 3600:
        return False, ""
    left = _field(current, "title") + " " + _field(current, "raw_text")[:3000]
    right = _field(prior, "title") + " " + _field(prior, "raw_text")[:3000]
    for first, second in _OPPOSITE_STATUS:
        if ((first.search(left) and second.search(right)) or
            (first.search(right) and second.search(left))):
            return False, ""
    # Fresh counts imply a material update even with otherwise shared prose.
    a_numbers = set(re.findall(r"(?<!\w)\d{1,6}(?!\w)", left))
    b_numbers = set(re.findall(r"(?<!\w)\d{1,6}(?!\w)", right))
    if a_numbers != b_numbers:
        return False, ""
    la, lb = _meaningful_stems(current), _meaningful_stems(prior)
    shared = la & lb
    if len(shared) >= 6 and len(shared) / max(1, min(len(la), len(lb))) >= 0.60:
        return True, f"MONITORING_SAME_DONOR_CONSECUTIVE_SOURCE_STORY_2346 shared={len(shared)}"
    return False, ""


__all__ = ["childhood_reflection_without_event_2346", "same_source_reflective_continuation_2346", "same_source_telegram_thread_2346"]
