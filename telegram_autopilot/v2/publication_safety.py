"""Detect internal AI refusal/selection comments before they become Telegram posts.

Must be a deterministic, channel-independent safety fence. Do not classify an
ordinary factual report or an attributed quotation merely for using "відмова".
"""
from __future__ import annotations

import re

_REJECTION = re.compile(
    r"(?:не\s+(?:стосується|відповідає)\s+(?:тематиц[іи]|запорізьк)|"
    r"не\s+відповідає\s+тематиц[іи]|"
    r"(?:матеріал|новин[ау]|публікаці[яю])\s+(?:не\s+)?(?:відхилен[ао]|нерелевантн[ао])|"
    r"(?:відхилити|не\s+публікувати)\s+(?:цей\s+)?матеріал|"
    r"не\s+(?:підходить|придатн[ао])\s+для\s+(?:цього\s+)?канал[уа])", re.I,
)
_PREFIX = re.compile(r"^\s*(?:відповідь\s*:|answer\s*:|decision\s*:|reject\s*:)", re.I)
_SOURCE_ABSENCE = re.compile(
    r"(?iu)(?:^|[.!?]\s*)"
    r"(?:це\s+)?джерело\s+(?:не\s+(?:містить|надає|має|дає)|"
    r"не\s+міститься\s+в)\s+"
    r"(?:жодн\w*\s+)?(?:інформаці\w*|відомост\w*|дан\w*|факт\w*)"
)
_META_SUBJECT = re.compile(r"(?iu)\b(?:джерел\w*|матеріал\w*|текст\w*|новин\w*|тематиц\w*|канал\w*)\b")
_RELEVANCE_DENIAL = re.compile(
    r"(?iu)(?:не\s+(?:стосується|відповідає|містить|підходить|належить)|"
    r"не\s+(?:пов'язаний|пов’язаний|релевантний)|"
    r"поза\s+(?:темою|тематикою)|"
    r"відсутн\w*\s+(?:місцев\w*\s+)?(?:факт\w*|інформаці\w*))"
)
_NO_POST = re.compile(
    r"(?iu)\b(?:"
    r"(?:пост|допис|публікаці\w*|новин\w*)\s+не\s+"
    r"(?:створю\w*|форму\w*|готую\w*|публіку\w*|буде\s+(?:створен\w*|опублікован\w*))|"
    r"(?:пост|допис|публікаці\w*)\s+"
    r"(?:не\s+буде|буде\s+відхилен\w*)|"
    r"(?:не\s+створювати|не\s+публікувати|не\s+готувати)\s+"
    r"(?:пост|допис|публікаці\w*)|"
    r"(?:тому|отже|відтак)\s+(?:цей\s+)?(?:пост|допис|матеріал|публікаці\w*)"
    r"\s+(?:не\s+створю\w*|не\s+публіку\w*|відхилен\w*)"
    r")\b"
)
_ENGLISH_REJECTION = re.compile(
    r"(?i)\b(?:no\s+(?:post|article)\s+will\s+be\s+(?:created|published)|"
    r"(?:do\s+not|don't)\s+publish\s+(?:this\s+)?(?:post|article)|"
    r"source\s+(?:does\s+not|doesn't)\s+contain\s+relevant\s+(?:local\s+)?information)\b"
)
_ATTRIBUTED_QUOTE = re.compile(
    r"(?iu)[«“\"].{5,180}[»”\"]\s*[,.:]?\s*(?:сказав|сказала|"
    r"повідомив|повідомила|пояснив|пояснила|розповів|розповіла)"
)

def is_ai_rejection_text(text: str) -> bool:
    """Return True for AI meta decisions, False for attributed reporting.

    The incident "Джерело не містить ... Тому пост не створюється"
    is a rejection even without an "Відповідь:" prefix.
    """
    value = str(text or "").strip()
    if not value:
        return False  # Existing TEXT_MISSING guard handles blank text.
    low = value.casefold()
    collapsed = " ".join(low.split())
    if _ATTRIBUTED_QUOTE.search(value) and not _SOURCE_ABSENCE.search(collapsed):
        return False
    # Direct command/decision from a generator, not a newspaper quoting one.
    if _SOURCE_ABSENCE.search(collapsed) and (
        _NO_POST.search(collapsed) or
        (_RELEVANCE_DENIAL.search(collapsed) and len(collapsed) < 1100)
    ):
        return True
    if _ENGLISH_REJECTION.search(collapsed) and len(collapsed) < 650:
        return True
    if _PREFIX.search(value) and (_REJECTION.search(collapsed) or _NO_POST.search(collapsed) or len(value) < 90):
        return True
    if re.search(r"(?iu)(?:цей\s+матеріал|ця\s+новина|цей\s+текст).{0,100}(?:не\s+стосується|не\s+відповідає|не\s+підходить)", collapsed):
        return True
    if len(collapsed) <= 450 and _NO_POST.search(collapsed) and (
        _META_SUBJECT.search(collapsed) or collapsed.startswith(("тому ", "отже ", "пост ", "допис "))
    ):
        return True
    if len(collapsed) <= 320 and _REJECTION.search(collapsed) and any(
        word in collapsed for word in ("темати", "канал", "матеріал", "публікац")
    ):
        return True
    return False
