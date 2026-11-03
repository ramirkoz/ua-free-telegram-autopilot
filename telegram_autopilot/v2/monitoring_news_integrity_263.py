"""2.2.63: source-owned municipal news vs copied channel solicitation.

Attested in real LIVE records #87658 (Halloween social-media solicitation),
#87615 (outside channel's "swipe cards/comment" call), and #87338
(unverified restaurant complaint with deliberately unexplained photo teaser).

Do not invent a missing image fact, convert third-party "we" into the operator,
or interpret social-engagement requests as community news. These guards are
conservative, local, and used only for monitoring channels.
"""
from __future__ import annotations

import re
from typing import Any


def _field(row: Any, key: str) -> str:
    try:
        item = row[key]
    except (KeyError, TypeError, IndexError):
        item = getattr(row, key, "")
    return str(item or "")


_PLATFORM = re.compile(r"(?iu)\b(?:whatsapp|instagram|tiktok|threads|facebook|інстаграм|тік\s*ток|фейсбук|вотсап)\b")
_EXTERNAL_SOLICIT = re.compile(
    r"(?iu)\b(?:діліться\s+(?:світлинами|фото|історіями|знімками)|"
    r"підписуй(?:теся|тесь|ся)\s+(?:на|тут)|"
    r"ми\s+(?:є|в|у)\s+(?:whatsapp|instagram|tiktok|threads)|"
    r"ми\s+в\s*[📲📱]\s*(?:whatsapp|instagram|tiktok|threads))\b"
)
_SUBSTANTIVE_EVENT = re.compile(
    r"(?iu)\b(?:відкрили|відкрива\w*|запустили|запрацював|запрацювала|"
    r"ухвалили|опублікували|оголосили|підписали|провели|"
    r"організували|передали|пошкодили|постраждали|"
    r"відновили|змінили|працюватиме|розпочнеться|"
    r"розпочали|повідомили\s+про)\b"
)
_OUTPUT_CTA = re.compile(
    r"(?iu)\b(?:"
    r"гортайте\s+(?:картки|слайди|галерею)|"
    r"діліться\s+(?:світлинами|фотографіями|фото|знімками|"
    r"історіями)(?:\s+[^.!?\n]{0,65})?(?:у|в)\s+коментарях|"
    r"діліться\s+світлинами|"
    r"підписуй(?:теся|тесь|ся)\s+(?:на\s+нас|на\s+(?:наш|цей)\s+канал)|"
    r"(?:ми\s+(?:є|в|у)|читайте\s+нас\s+(?:в|у))\s+"
    r"(?:whatsapp|instagram|tiktok|threads|facebook)"
    r")\b"
)
# A particular live personal complaint used a photograph as an unexplained
# allegation and named a private restaurant. Neither source text nor title
# identifies the alleged object. Do not infer it from images.
_VAGUE_COMPLAINT = re.compile(r"(?iu)[«“\"]комплімент\s+від\s+шефа[»”\"]")
_UNVERIFIED_TESTIMONY = re.compile(
    r"(?iu)\b(?:ось\s+що\s+пишуть\s+\w+|клієнт\w*\s+скарж\w*|"
    r"нам\s+написал\w*|у\s+скарзі\s+зазнач\w*)\b"
)

def monitoring_source_promo_reason(article: Any) -> str:
    """Reject ONLY brief *source-owned* channel advertising with no actual event."""
    raw = _field(article, "raw_text").strip()
    if not raw or len(raw) > 350:
        return ""
    platforms = {match.group(0).casefold() for match in _PLATFORM.finditer(raw)}
    if len(platforms) < 2 or not _EXTERNAL_SOLICIT.search(raw):
        return ""
    if _SUBSTANTIVE_EVENT.search(raw):
        return ""
    return "MONITORING_SOURCE_CHANNEL_SELF_PROMO_263"

def monitoring_unverified_teaser_reason(article: Any) -> str:
    """A photo-dependent reputational allegation without textual description."""
    source = _field(article, "raw_text")
    if _VAGUE_COMPLAINT.search(source) and _UNVERIFIED_TESTIMONY.search(source):
        return "MONITORING_UNVERIFIED_COMPLAINT_TEASER_263"
    return ""

def monitoring_copied_cta_issue(text: str) -> str:
    """Never publish another channel's 'we', carousel or engagement instruction."""
    if _OUTPUT_CTA.search(str(text or "")):
        return "MONITORING_COPIED_CHANNEL_CTA_263: сторонній заклик чи реклама перенесені в голос нашого каналу"
    return ""

MONITORING_NEWS_INTEGRITY_RULE_263 = (
    "2.2.63 ГОЛОС КАНАЛУ: SOURCE може містити рекламу власного WhatsApp, "
    "Instagram, TikTok, Threads, заклики «гортайте картки», «діліться фото», "
    "«підписуйтеся на нас». Це заклики ЧУЖОГО каналу: НЕ повторюй їх, "
    "НЕ пиши «ми є у...» від імені нашого каналу. Переказуй лише реальну "
    "підтверджену подію. Не називай непрочитану деталь на фото доведеним "
    "фактом; якщо SOURCE не розкриває головний зміст скарги або звинувачення, "
    "не вигадуй його і не подавай натяк як завершену новину. "
    "В українських числових вікових інтервалах пиши «учасники віком "
    "від 11 до 18 років», а не «11–18 рік»."
)
