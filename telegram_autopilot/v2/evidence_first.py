"""Evidence-first monitoring contracts (2.2.0).

Pure validation functions. They never synthesize missing facts or modify source
content. Decisions are conservative when source event boundaries are uncertain.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping
from .event_boundaries import classify_event_boundaries

_TRAFFIC = re.compile(r"(?iu)\b(?:дтп|аварі[яї]|зіткненн|рух\s+ускладнен)\b")
_LOST_ANIMAL = re.compile(r"(?iu)\b(?:хаскі|собак\w*|пес|цуцен\w*|тварин\w*)\b")
_LOST_PROPERTY = re.compile(r"(?iu)\b(?:загуби\w*|втратив\w*|знайшли)\b.{0,110}\b(?:папк\w*|документ\w*|ключ\w*|гаман\w*)\b|\bпапк\w*\s+з\s+документ\w*\b")
_ACTIVE_ATTACK = re.compile(r"(?iu)\b(?:рсзв|обстріл\w*|ракета\w*|каб\w*|бпла)\b.{0,85}\b(?:вдарил\w*|б[’']?ють|криють|летить|рухається)\b|\b(?:рсзв|обстріл\w*)\b.{0,55}\b(?:по|на)\s+\S+")
_VERIFIED_OUTCOME = re.compile(r"(?iu)\b(?:підтвердил\w*|пошкоджен\w*|загинул\w*|постраждал\w*|поранен\w*|ліквідувал\w*|рятувальник\w*\s+завершил\w*)\b")
_UNSUPPORTED_NO_INFORMATION = re.compile(r"(?iu)\b(?:інформац\w*\s+про\s+(?:наслідк\w*|пошкоджен\w*)\s+(?:наразі\s+)?не\s+надходил\w*|даних\s+про\s+(?:наслідк\w*|пошкоджен\w*)\s+немає)\b")
_VIDEO_CUE = re.compile(r"(?iu)\b(?:дивіться|перегляньте|друге|наступне)\b.{0,45}\bвідео\b|\bвідео\s+(?:сері[їю]|зустрічі|події)\b")


def _get(article: Any, key: str, default: Any = "") -> Any:
    try:
        result = article[key]
    except (TypeError, KeyError, IndexError):
        result = getattr(article, key, default)
    return result if result is not None else default


def _metadata(article: Any) -> dict[str, Any]:
    try:
        value = json.loads(str(_get(article, "article_layout_json", "") or "{}"))
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}


@dataclass(frozen=True)
class EvidenceDecision:
    reasons: tuple[str, ...]
    evidence: tuple[str, ...] = ()

    @property
    def allowed(self) -> bool:
        return not self.reasons


def assess_monitoring_source(article: Any, *, final_text: str = "") -> EvidenceDecision:
    """Reject conflated topics and unsupported post-factum claims.

    No inference from article discovery time to event completion is allowed.
    """
    title = str(_get(article, "title"))
    raw = str(_get(article, "raw_text"))
    source = (title + "\n" + raw).strip()
    final = str(final_text or "")
    reasons: list[str] = []
    evidence: list[str] = []
    boundaries = classify_event_boundaries(raw)
    if boundaries.ambiguous or (_LOST_ANIMAL.search(raw) and _LOST_PROPERTY.search(raw)):
        reasons.append("MONITORING_MULTIPLE_UNRELATED_NOTICES")
        evidence.extend(f"{span.category}:{span.start}-{span.end}" for span in boundaries.spans)
    if _ACTIVE_ATTACK.search(source) and not _VERIFIED_OUTCOME.search(source):
        # A short source cannot be promoted to a completed incident merely by
        # a writer adding 'today' or 'no information about consequences'.
        reasons.append("MONITORING_UNVERIFIED_ATTACK_OUTCOME")
        evidence.append("attack_without_verified_aftermath")
    if _UNSUPPORTED_NO_INFORMATION.search(final) and not _UNSUPPORTED_NO_INFORMATION.search(source):
        reasons.append("MONITORING_UNSUPPORTED_ABSENCE_CLAIM")
        evidence.append("absence_claim_not_in_source")
    return EvidenceDecision(tuple(dict.fromkeys(reasons)), tuple(evidence))


def video_required_by_copy(source: str, final_text: str = "") -> bool:
    """True when publication text refers to essential video evidence."""
    return bool(_VIDEO_CUE.search(str(source or "")) or _VIDEO_CUE.search(str(final_text or "")))


def assess_monitoring_media(article: Any, *, final_text: str = "") -> EvidenceDecision:
    """Fail closed for a Telegram video-dependent item with no bound media.

    The metadata may be absent on older migrations: block only when the text
    explicitly promises a video. A plain factual report is not blocked.
    """
    source_url = str(_get(article, "source_url")).casefold()
    if not ("t.me/" in source_url or "telegram.me/" in source_url):
        return EvidenceDecision(())
    source = str(_get(article, "raw_text"))
    final = str(final_text or "")
    if not video_required_by_copy(source, final):
        return EvidenceDecision(())
    layout = _metadata(article)
    media = str(_get(article, "media_json") or "").strip()
    from ..media import decode_media
    try:
        decoded = json.loads(media) if media else []
    except (TypeError, ValueError):
        decoded = []
    if not isinstance(decoded, list):
        decoded = []
    has_video = any(
        decode_media(str(encoded))[0] == "video"
        for encoded in decoded if isinstance(encoded, str)
    )
    tg = layout.get("telegram", {})
    if not isinstance(tg, dict):
        tg = {}
    if has_video:
        return EvidenceDecision(())
    # A source may explicitly signal a video placeholder with no download URL.
    # Images and posters do not satisfy the video requirement.
    if bool(tg.get("video_attachment_seen")):
        return EvidenceDecision(
            ("MONITORING_VIDEO_PENDING",), ("source_video_not_downloadable",)
        )
    return EvidenceDecision(("MONITORING_VIDEO_ATTACHMENT_UNBOUND",), ("video_cue_without_video",))
