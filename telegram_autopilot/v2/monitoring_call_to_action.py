"""Source-only veto for call-to-action posts in a news-only monitoring channel.

Operator rule (09.11.2026, confirmed 10.11): the regional channel publishes
facts — what happened, what was decided, what changed in a service. It does
not publish standalone invitations to a future event, ticket giveaways,
requests to fill in a survey or apply/register, or a reader's complaint
relayed by an aggregator.

A post is vetoed only when its PURPOSE is the call to action. A report of a
finished event, a decision, a schedule or service change is never vetoed here
even when it carries a link or a polite "запрошуємо" at the end: such posts
contain settled facts, and the wording check below requires the absence of
them. No model call, no channel names, no per-source rules.
"""
from __future__ import annotations

import re
from typing import Any


def _v(row: Any, key: str) -> str:
    try:
        return str(row[key] or "")
    except (KeyError, IndexError, TypeError):
        return str(getattr(row, key, "") or "")


# --- settled facts: when present, the post reports something that happened/changed.
_SETTLED_FACT = re.compile(
    r"(?iu)\b(?:відбув\w*|відбул\w*|пройшов|пройшла|пройшли|провели|провел\w+|завершив\w*|завершил\w*|"
    r"відкрил\w*|відкрит\w+\s+(?:нов|після)|відновил\w*|відзначил\w*|нагородил\w*|вручил\w*|"
    r"взяли\s+участь|взяв\s+участь|взяла\s+участь|ухвалил\w*|прийнял\w+\s+рішення|затвердил\w*|"
    r"загинул\w*|поранен\w*|постраждал\w*|пошкоджен\w*|зруйнован\w*|ліквідува\w*|евакуюва\w*|"
    r"затрима\w+|викрил\w*|повідомил\w+\s+про\s+підозру|судитимуть|засудил\w*)\b"
)
# --- service facts: a schedule, outage or availability change is news, not an advert.
_SERVICE_FACT = re.compile(
    r"(?iu)\b(?:графік\w*\s+(?:відключен|погодинн|подач|роботи|руху|прийому)|гпв|гав|черг\w+\s+\d|"
    r"відключен\w+|знеструмлен\w*|без\s+(?:світла|води|газу|тепла|опалення)|перекри\w+|обмежен\w+\s+рух|"
    r"не\s+працю\w+|тимчасово\s+(?:не|призупин|закрит)|призупин\w+|віднов\w+\s+(?:роботу|рух|подач)|"
    r"змін\w+\s+(?:графік|маршрут|розклад|режим)|аварі\w+|ремонтн\w+\s+робот\w*|"
    # Social support is a service of the community, not an advert: aid, payments,
    # compensation and their intake dates stay news.
    r"(?:грошов\w+|гуманітарн\w+|матеріальн\w+|фінансов\w+|адресн\w+)\s+допомог\w+|"
    r"допомог\w+\s+(?:впо|переселенц\w+|постраждал\w+|ветеран\w+|евакуйован\w+)|"
    r"виплат\w+|компенсац\w+|субсиді\w+|(?:продуктов|гігієнічн)\w+\s+набор\w+)\b"
)

_SURVEY_OBJECT = re.compile(r"(?iu)\b(?:опитуванн\w+|анкет\w+|анкетуванн\w+|онлайн-?форм\w+)\b")
_SURVEY_CALL = re.compile(
    r"(?iu)(?:\bпройти\b|\bпройдіть\b|взяти\s+участь|візьміть\s+участь|долуч\w+|заповн\w+|"
    r"запрошу\w+|просимо|просять|звертається\s+з\s+проханням|ваша\s+думка|за\s+посиланням|"
    r"kobotoolbox|forms\.gle|docs\.google\.com/forms)"
)
_SURVEY_RESULT = re.compile(r"(?iu)\b(?:результат\w+|підсумк\w+)\s+(?:\w+\s+){0,2}(?:опитуванн|анкетуванн)")

_INVITE = re.compile(
    r"(?iu)(?:\bзапрошу\w+|\bзапрошен\w+\s+всі|приходьте|завітайте|чекаємо\s+на\s+вас|не\s+пропустіть|"
    r"\bафіш\w+|вхід\s+вільний|\bквитк\w+|поверніться\s+у)"
)
_GIVEAWAY = re.compile(r"(?iu)\b(?:розіграш\w*|розігруємо|розіграємо|giveaway)\b")
_FUTURE_EVENT = re.compile(
    r"(?iu)\b(?:відбудеться|відбудуться|пройде|пройдуть|прозвучить|стартує|розпочнеться|"
    r"триватиме|чекатиме|об?\s*\d{1,2}[:.]\d{2})\b"
)
_APPLY_CALL = re.compile(
    r"(?iu)(?:оголошу\w+\s+набір|триває\s+набір|\bнабір\s+(?:на|до|у)\b|реєстрац\w+\s+(?:на|відкрит|триває|учасник)|"
    r"триває\s+реєстрац\w+|зареєструват\w+|зареєструйтес\w*|пода(?:ти|вайте|йте)\s+заявк\w+|"
    r"приймаються\s+заявк\w+|прийом\s+заявок|заявки\s+приймають\w*|шукаємо\s+(?:волонтер|працівник|учасник))"
)

_READER_COMPLAINT = re.compile(
    r"(?iu)(?:пишіть\s+нам|надсилайте\s+нам|надішліть\s+нам|\bагов\b|"
    r"(?:підписни\w+|читач\w*|мешкан\w+)\s+(?:скарж\w+|нарік\w+|обурен\w*)|"
    r"навіть\s+не\s+(?:\"?пахне|вмикав|вмикал)|куди\s+дивиться|доки\s+це\s+буде)"
)
_OFFICIAL_VOICE = re.compile(
    r"(?iu)\b(?:повідоми\w+\s+(?:в|у)\s|за\s+даними|за\s+інформацією|ова\b|овa\b|дснс|поліці\w+|прокуратур\w+|"
    r"міськрад\w*|міськ\w+\s+рад\w+|сільськ\w+\s+рад\w+|селищн\w+\s+рад\w+|військов\w+\s+адміністрац\w+|"
    r"обленерго|водоканал\w*|тепломереж\w*|укренерго|комунальн\w+\s+підприємств\w+)\b"
)


def call_to_action_reason(article: Any) -> str:
    """Return a stable reject code, or '' when the post reports facts."""
    title = _v(article, "title")
    body = _v(article, "raw_text")
    text = body if title and title in body else f"{title}\n{body}"
    if not text.strip():
        return ""
    settled = bool(_SETTLED_FACT.search(text))
    service = bool(_SERVICE_FACT.search(text))

    # A reader's grievance relayed without any official confirmation.
    if _READER_COMPLAINT.search(text) and not _OFFICIAL_VOICE.search(text):
        return "MONITORING_READER_COMPLAINT"

    if _SURVEY_OBJECT.search(text) and _SURVEY_CALL.search(text) and not _SURVEY_RESULT.search(text):
        return "MONITORING_SURVEY_INVITATION"

    if settled or service:
        return ""

    if _GIVEAWAY.search(text):
        return "MONITORING_GIVEAWAY"
    if _APPLY_CALL.search(text):
        return "MONITORING_APPLICATION_CALL"
    if _INVITE.search(text) and _FUTURE_EVENT.search(text):
        return "MONITORING_FUTURE_EVENT_INVITATION"
    return ""
