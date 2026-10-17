"""Evidence-first monitoring contracts (2.2.0).

Pure validation functions. They never synthesize missing facts or modify source
content. Decisions are conservative when source event boundaries are uncertain.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping

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
    if _LOST_ANIMAL.search(raw) and _LOST_PROPERTY.search(raw):
        reasons.append("MONITORING_MULTIPLE_UNRELATED_NOTICES")
        evidence.append("lost_animal+lost_property")
    if _ACTIVE_ATTACK.search(source) and not _VERIFIED_OUTCOME.search(source):
        # A short source cannot be promoted to a completed incident merely by
        # a writer adding 'today' or 'no information about consequences'.
        reasons.append("MONITORING_UNVERIFIED_ATTACK_OUTCOME")
        evidence.append("attack_without_verified_aftermath")
    if _UNSUPPORTED_NO_INFORMATION.search(final) and not _UNSUPPORTED_NO_INFORMATION.search(source):
        reasons.append("MONITORING_UNSUPPORTED_ABSENCE_CLAIM")
        evidence.append("absence_claim_not_in_source")
    return EvidenceDecision(tuple(dict.fromkeys(reasons)), tuple(evidence))


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
    if not (_VIDEO_CUE.search(source) or _VIDEO_CUE.search(final)):
        return EvidenceDecision(())
    layout = _metadata(article)
    media = str(_get(article, "media_json") or "").strip()
    has_declared_media = bool(media and media not in {"[]", "{}", "null"})
    tg = layout.get("telegram", {})
    if not isinstance(tg, dict):
        tg = {}
    explicit_count = max(
        int(layout.get("media_count", 0) or 0),
        int(tg.get("media_count", 0) or 0),
    )
    if has_declared_media or explicit_count:
        return EvidenceDecision(())
    return EvidenceDecision(("MONITORING_VIDEO_ATTACHMENT_UNBOUND",), ("video_cue_without_media",))
