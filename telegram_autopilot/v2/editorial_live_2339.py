"""2.3.39: source-only editorial false-positive and confirmed-event controls.

Evidence comes from original source title/body, never the generated rewrite.
This module has no per-channel IDs, live network requests, or Data mutations.
The semantic gate is intentionally narrow: short time window, matching source
facts, matching headline subject, no fresh outcome or substantive numbers, and
only actually COMMITTED Telegram posts as evidence.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any


def _field(row: Any, key: str) -> str:
    try:
        return str(row[key] or "")
    except (KeyError, IndexError, TypeError):
        return str(getattr(row, key, "") or "")


_PET_RESCUE_TITLE = re.compile(
    r"(?iu)(?:\b(?:cats?|kittens?|dogs?|pupp(?:y|ies)|pets?)\b.{0,110}"
    r"\b(?:rescu(?:e|es|ed)|saved?|found|trapped|reunited|missing)\b|"
    r"\b(?:rescu(?:e|es|ed)|saved?|found|trapped|reunited|missing)\b.{0,110}"
    r"\b(?:cats?|kittens?|dogs?|pupp(?:y|ies)|pets?)\b|"
    r"\b(?:кот\w*|кішк\w*|собак\w*)\b.{0,95}"
    r"\b(?:врятува\w*|знайшл\w*|знайден\w*|застряг\w*|зник\w*)\b)"
)
_PET_RESCUE_BODY = re.compile(
    r"(?iu)\b(?:rescu(?:e|es|ed)|saved?|found|trapped|missing|reunion|"
    r"animal\s+rescue|veterinary\s+clinic|"
    r"врятува\w*|порятун\w*|знайден\w*|застряг\w*)\b"
)
# An original creative/engineering mechanism is materially different from
# the routine rescue chronicle. Do not veto actual unusual animal behaviour.
_CREATIVE_MECHANISM = re.compile(
    r"(?iu)\b(?:new\s+(?:robot|sensor|device|prototype|invention|technology)|"
    r"robotic\s+rescue|innovative\s+rescue\s+device|"
    r"(?:original|creative)\s+(?:campaign|advertising|design|installation)|"
    r"scientists?\s+(?:discover|demonstrate)|animal\s+behavio(?:u)?r\s+(?:study|experiment)|"
    r"нов\w*\s+(?:робот\w*|сенсор\w*|пристр\w*|винахід\w*)|"
    r"креативн\w*\s+кампані\w*|мистецьк\w*\s+інсталяц\w*)\b"
)


def creative_routine_pet_rescue_reason(article: Any) -> str:
    """Do not make an ordinary lost/rescued pet a creative-channel story.

    Exception requires source-grounded *substantive* creative or technical
    subject matter, not merely 'heartwarming' language or four days missing.
    A truly novel animal story still goes to the normal human-calibrated AI.
    """
    title = _field(article, "title")[:600]
    raw = _field(article, "raw_text")[:5000]
    if (title and raw and _PET_RESCUE_TITLE.search(title)
            and _PET_RESCUE_BODY.search(raw)
            and not _CREATIVE_MECHANISM.search(title + "\n" + raw)):
        return "CREATIVE_ROUTINE_PET_RESCUE_NOT_CHANNEL_FIT_2339"
    return ""


_APPEAL_TITLE = re.compile(
    r"(?iu)\b(?:оприлюдніть|оприлюднить|опублікуйте|поясніть|повідомте|"
    r"дайте\s+(?:відповідь|інформацію)|просимо\s+(?:надати|пояснити|оприлюднити)|"
    r"please\s+(?:publish|explain|tell\s+us))\b"
)
_APPEAL_CONTEXT = re.compile(
    r"(?iu)(?:\b(?:немає|відсутн\w*).{0,80}(?:інформац\w*|відповід\w*)\b|"
    r"\b(?:інформац\w*|відповід\w*).{0,80}\bнемає\b|"
    r"\b(?:люди|мешканці)\s+(?:просять|вимагають)\b|"
    r"\b(?:без\s+відповід\w*|чат.бот.{0,110}запит\w*|запит\w*\s+без\s+відповід)\b)"
)


def monitoring_appeal_not_news_reason(article: Any) -> str:
    """A channel's plea to officials is not a verified official update."""
    title = _field(article, "title")[:700]
    raw = _field(article, "raw_text")[:3300]
    if title and raw and _APPEAL_TITLE.search(title) and _APPEAL_CONTEXT.search(raw):
        return "MONITORING_READER_APPEAL_NOT_VERIFIED_NEWS_2339"
    return ""


_TOKEN = re.compile(r"[a-zа-яіїєґ][a-zа-яіїєґ’'-]{3,}", re.I | re.U)
_STOP = {
    "сьогодні", "вчора", "через", "після", "разом", "також", "можуть",
    "можна", "навіть", "міста", "області", "україни", "нашого", "новини",
    "подробиці", "деталі", "джерело", "джерела", "роботи", "роботі",
    "працює", "працюють", "продовж", "відтак", "були", "буде", "вони",
    "telegram", "instagram", "facebook", "whatsapp", "tiktok", "youtube",
    "update", "updated", "news", "today", "yesterday", "about", "after",
    "before", "their", "there", "these", "those", "where", "which",
}
_SOURCE_LINK = re.compile(r"https?://\S+", re.I)
_SUBSTANTIVE_NEW_STATUS = re.compile(
    r"(?iu)\b(?:відновлено|відновили|поновили|підключено|завершено|"
    r"скасовано|відкрито|відкрили|знято\s+обмеження|"
    r"restored|reopened|resumed|cancelled|canceled|completed)\b"
)
_STATUS_CANCEL = re.compile(r"(?iu)\b(?:скасовано|скасували|cancelled|canceled)\b")
_STATUS_INTRODUCE = re.compile(r"(?iu)\b(?:запроваджено|запровадили|введено|introduced|imposed)\b")
_NUMBERS = re.compile(r"(?<!\w)\d+(?:[,.]\d+)?(?!\w)")
_STREET = re.compile(
    r"(?iu)\b(?:вул(?:иц[яі])?\.?|провул\w*|просп\w*|street|avenue)\s+"
    r"([а-яіїєґa-z][а-яіїєґa-z'-]{3,})"
)


def _terms(text: str) -> set[str]:
    text = _SOURCE_LINK.sub(" ", str(text or "")[:5000]).casefold()
    result: set[str] = set()
    for word in _TOKEN.findall(text):
        if len(word) < 5 or word in _STOP:
            continue
        if word.startswith(("instagram", "facebook", "telegram", "whatsapp", "tiktok", "youtube")):
            continue
        stem = word[:7] if len(word) >= 9 else word[:6] if len(word) >= 7 else word[:5]
        if stem not in _STOP:
            result.add(stem)
    return result


def _facts(row: Any) -> str:
    return (_field(row, "title") + " " + _field(row, "raw_text")[:3500]).strip()


def source_same_event_without_update(current: Any, prior: Any) -> bool:
    """High-precision same-event proof for closely timed *different* sources.

    Shared topic alone is insufficient. Six source-owned factual terms, at
    least 60% containment of the shorter account and two title anchors
    are required. A new confirmed status, number or different street wins
    over similarity. This is not a broad embedding/AI topic classifier.
    """
    from .editorial_live_2341 import same_zaporizhzhia_daily_attack_bulletin_2341
    if same_zaporizhzhia_daily_attack_bulletin_2341(current, prior):
        return True
    if _field(current, "source_id") == _field(prior, "source_id"):
        return False
    current_text, prior_text = _facts(current), _facts(prior)
    a, b = _terms(current_text), _terms(prior_text)
    if not a or not b:
        return False
    shared = a & b
    if len(shared) < 6 or len(shared) / min(len(a), len(b)) < 0.60:
        return False
    if len(_terms(_field(current, "title")) & _terms(_field(prior, "title"))) < 2:
        return False
    if _SUBSTANTIVE_NEW_STATUS.search(current_text) and not _SUBSTANTIVE_NEW_STATUS.search(prior_text):
        return False
    if (_STATUS_CANCEL.search(current_text) and _STATUS_INTRODUCE.search(prior_text)
            or _STATUS_INTRODUCE.search(current_text) and _STATUS_CANCEL.search(prior_text)):
        return False
    # A change in an explicit source-reported figure may be a real update.
    current_numbers = set(_NUMBERS.findall(_SOURCE_LINK.sub(" ", current_text)))
    prior_numbers = set(_NUMBERS.findall(_SOURCE_LINK.sub(" ", prior_text)))
    if current_numbers - prior_numbers:
        return False
    current_streets = {x.casefold() for x in _STREET.findall(current_text)}
    prior_streets = {x.casefold() for x in _STREET.findall(prior_text)}
    if current_streets and prior_streets and current_streets.isdisjoint(prior_streets):
        return False
    return True


def recent_committed_source_duplicate(
    store: Any, channel_id: int, article_id: int, article: Any, *, window_hours: int = 6
) -> int:
    """READ-ONLY lookup against Telegram COMMITTED, never READY/UNKNOWN.

    Caller may mark the returned article as a duplicate before sending;
    this function never writes to the operator database.
    """
    # Honor tighter operator channel windows; never expand them to six hours.
    hours = min(6, int(window_hours))
    if hours <= 0:
        return 0
    with store.connect() as con:
        rows = con.execute(
            """SELECT a.id,a.source_id,a.title,a.raw_text,a.source_published_at,a.published_at
               FROM articles a
               WHERE a.channel_id=? AND a.id<>? AND a.stage='PUBLISHED'
                 AND a.published_at<>''
                 AND datetime(a.published_at)>=datetime('now',?)
                 AND (
                   EXISTS (SELECT 1 FROM publication_delivery_journal d
                           WHERE d.article_id=a.id AND d.channel_id=a.channel_id
                             AND d.state='COMMITTED')
                   OR EXISTS (SELECT 1 FROM delivery_receipt_archive h
                              WHERE h.article_id=a.id AND h.channel_id=a.channel_id
                                AND h.state='COMMITTED')
                 )
               ORDER BY datetime(a.published_at) DESC LIMIT 120""",
            (int(channel_id), int(article_id), f'-{hours} hours'),
        ).fetchall()
    now = datetime.now(timezone.utc)
    for row in rows:
        try:
            published = datetime.fromisoformat(_field(row, "published_at").replace("Z", "+00:00"))
            if published.tzinfo is None:
                continue
            lag = now - published.astimezone(timezone.utc)
            if lag < timedelta(0) or lag > timedelta(hours=hours):
                continue
        except ValueError:
            continue
        if source_same_event_without_update(article, row):
            return int(row["id"])
    return 0
