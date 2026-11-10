"""v2.3.22: no classifieds or stand-alone announcements in regional news.

This is a source-only editorial boundary. A genuine verified news event and
official service disruption are not a private ad merely for containing the
word "оголосили". Reject lost-and-found, contact-for-return, commercial
listings, personal recruitment, bare invitations and third-party allegations.
Names/phones are never copied to logs.
"""
from __future__ import annotations

import re
from typing import Any


_LOST_FOUND = re.compile(
    r"(?iu)(?:"
    r"\b(?:знайшл\w*|знайден\w*|загубил\w*|загублен\w*|"
    r"втратив\w*|втрачено|втрачен\w*|чий|чиї|поверніть)\b"
    r"[^.!?\n]{0,140}\b(?:документ\w*|паспорт\w*|посвідченн\w*|"
    r"ключ\w*|гаманц\w*|сумк\w*|телефон\w*|реч\w*|собак\w*|кот\w*)\b"
    r"|"
    r"\b(?:документ\w*|паспорт\w*|посвідченн\w*|ключ\w*|гаманц\w*)\b"
    r"[^.!?\n]{0,100}\b(?:знайден\w*|знайшл\w*|загубил\w*|"
    r"втрачен\w*|повернут\w*|на\s+ім[’']?я)\b"
    r")"
)
_PRIVATE_CLASSIFIED = re.compile(
    r"(?imu)(?:^|[.!?]\s+)(?:продам|продаю|куплю|"
    r"здам|здаю|зніму|обміняю|віддам|шукаю\s+"
    r"(?:житл\w*|квартир\w*|будинок|авто|робот\w*)|"
    r"надаю\s+послуг\w*|пропоную\s+послуг\w*)\b"
)
_PRIVATE_RECRUITMENT = re.compile(
    r"(?iu)(?:\bвакансі\w*\b|"
    r"\b(?:шукаємо|потрібн\w*|запрошуємо)\s+"
    r"(?:працівник\w*|робітник\w*|воді\w*|продавц\w*|"
    r"менеджер\w*|кухар\w*|майстр\w*|на\s+роботу)\b|"
    r"\bнабір\s+(?:співробітник\w*|персонал\w*)\b)"
)
_BARE_INVITATION = re.compile(
    r"(?iu)(?:"
    r"\bзапрошуємо\s+(?:вас|всіх|жител\w*|мешканц\w*|охоч\w*|на)\b|"
    r"\b(?:приходьте|записуйтесь|записуйтеся|реєструйтеся|"
    r"долучайтеся|долучайтесь)\s+(?:на|до|для)\b|"
    r"\b(?:відкрит\w*\s+реєстраці\w*|реєстраці\w*\s+відкрит\w*|"
    r"оголошено\s+набір|триває\s+набір)\b"
    r")"
)
_TICKET_OR_EVENT_AD = re.compile(
    r"(?iu)\b(?:квитк\w*|реєстраці\w*|запис\w*|афіш\w*|"
    r"безкоштовн\w*\s+вхід)\b"
)
_SALE_AD = re.compile(
    r"(?iu)(?:"
    r"\b(?:розпродаж\w*|знижк\w*|акційн\w*\s+цін\w*)\b"
    r"[^.!?\n]{0,140}\b(?:купуйте|встигніть|завітайте|придбайте|"
    r"замовляйте|до\s*\d{1,2}\s*%|грн)\b|"
    r"\b(?:купуйте|завітайте|придбайте)\b[^.!?\n]{0,100}"
    r"\b(?:знижк\w*|розпродаж\w*|грн)\b)"
)
_PHONE = re.compile(r"(?<!\d)(?:\+?38[\s().-]*)?0\d{2}(?:[\s().-]*\d){7}(?!\d)")
_PRIVATE_ACCUSATION = re.compile(
    r"(?iu)(?:покинул\w*|прив[’']?язал\w*|залишил\w*)"
    r"[^.!?\n]{0,120}(?:собак\w*|тварин\w*|цуцен\w*)"
)
_PURE_ANNOUNCEMENT = re.compile(
    r"(?iu)^\s*(?:[📢🔔❗️]\s*)?(?:оголошення|"
    r"дошка\s+оголошень|афіша\s+(?:заходів|подій))\b"
)

_GENERIC_GREETING = re.compile(
    r"(?iu)(?:\b(?:зі?\s+святом|вітаємо\s+з\s+днем|"
    r"всім\s+(?:гарного|приємного|смачного)|"
    r"смачного\s+обіду)\b)"
)


def _field(article: Any, key: str) -> str:
    try:
        return str(article[key] or "")
    except (KeyError, IndexError, TypeError):
        return str(getattr(article, key, "") or "")


def no_announcement_reason_2322(article: Any) -> str:
    """Block only source-owned stand-alone announcements, never AI impressions."""
    original = (_field(article, "title") + "\n" + _field(article, "raw_text"))[:10000]
    if not original.strip():
        return ""
    if _LOST_FOUND.search(original):
        return "MONITORING_CLASSIFIED_LOST_FOUND_2322"
    if _PRIVATE_ACCUSATION.search(original) and _PHONE.search(original):
        return "MONITORING_PRIVATE_ALLEGATION_CONTACT_2322"
    if _PURE_ANNOUNCEMENT.search(original):
        return "MONITORING_STANDALONE_ANNOUNCEMENT_2322"
    if _PRIVATE_CLASSIFIED.search(original):
        return "MONITORING_PRIVATE_CLASSIFIED_2322"
    if _PRIVATE_RECRUITMENT.search(original):
        return "MONITORING_JOB_ADVERTISEMENT_2322"
    if _SALE_AD.search(original):
        return "MONITORING_SALES_ADVERTISEMENT_2322"
    # Bare prospective participation notice, not a report about a finished event.
    if _BARE_INVITATION.search(original):
        return "MONITORING_EVENT_INVITATION_2322"
    if _GENERIC_GREETING.search(original) and len(original) < 500:
        return "MONITORING_GREETING_2322"
    return ""
