from __future__ import annotations

import math
import re
import sqlite3
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from .feedback import FEEDBACK_WINDOW_DAYS, FeedbackService
from .storage import V2Store

ADMIN_LIKE_WEIGHT = 1.0
ADMIN_DISLIKE_WEIGHT = -2.0
AUDIENCE_TOPIC_WEIGHT = 0.35
SOURCE_AUDIENCE_WEIGHT = 0.12
STYLE_WINDOW_DAYS = 7
MAX_STYLE_EXAMPLES = 4

_WORD_RE = re.compile(r"[0-9A-Za-zА-Яа-яІіЇїЄєҐґЁёЫыЭэЪъ'’+-]{3,}", re.U)
_STOPWORDS = {
    "але", "або", "без", "був", "була", "були", "було", "буде", "для", "його", "її", "їх",
    "після", "про", "при", "так", "також", "цей", "ця", "це", "через", "щоб", "який", "яка",
    "які", "новий", "нова", "нове", "the", "and", "for", "from", "with", "that", "this", "was",
    "were", "will", "have", "has", "had", "about", "into", "after", "before", "new", "says", "said",
    "что", "это", "после", "который", "которая", "будет", "также", "или",
}


def _v(row: Mapping[str, Any] | Any, key: str, default: Any = "") -> Any:
    try:
        value = row[key]
    except Exception:
        value = getattr(row, key, default)
    return default if value is None else value


def _row_int(row: Mapping[str, Any] | Any, key: str) -> int:
    try:
        return max(0, int(_v(row, key, 0) or 0))
    except Exception:
        return 0


def _parse_dt(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _tokens(value: str) -> set[str]:
    out: set[str] = set()
    for match in _WORD_RE.finditer(str(value or "").casefold().replace("’", "'")):
        token = match.group(0).strip("-'–+")
        if len(token) < 3 or token in _STOPWORDS:
            continue
        if token.endswith("s") and token.isascii() and len(token) > 5:
            token = token[:-1]
        out.add(token)
    return out


def similarity_parts(left: str, right: str) -> tuple[float, int]:
    a, b = _tokens(left), _tokens(right)
    if not a or not b:
        return 0.0, 0
    overlap = a & b
    shared = len(overlap)
    jaccard = shared / max(1, len(a | b))
    containment = shared / max(1, min(len(a), len(b)))
    return min(1.0, 0.48 * jaccard + 0.52 * containment), shared


def _candidate_text(article: Any) -> str:
    return "\n".join(part for part in (
        str(_v(article, "title", "")), str(_v(article, "raw_text", ""))[:6000], str(_v(article, "event_summary", ""))[:1200]
    ) if part)


def _feedback_text(row: Any) -> str:
    return "\n".join(part for part in (
        str(_v(row, "title", "")), str(_v(row, "raw_text", ""))[:6000], str(_v(row, "event_summary", ""))[:1200]
    ) if part)


def topic_feedback_signal(row: Any) -> float:
    """Admin/editor topic preference only. Fire deliberately does not enter topic learning."""
    return _row_int(row, "likes") * ADMIN_LIKE_WEIGHT + _row_int(row, "dislikes") * ADMIN_DISLIKE_WEIGHT


def style_feedback_signal(row: Any) -> float:
    """Only admin/editor fire teaches writing style. Audience never teaches prose directly."""
    return float(_row_int(row, "fires"))


def audience_raw_rate(row: Any) -> float:
    views = _row_int(row, "views")
    if views <= 0:
        return 0.0
    positive = _row_int(row, "audience_positive")
    negative = _row_int(row, "audience_negative")
    fires = _row_int(row, "audience_fires")
    other = _row_int(row, "audience_other")
    forwards = _row_int(row, "forwards")
    replies = _row_int(row, "replies")
    effective = positive + 0.5 * fires + 0.25 * other + 2.0 * forwards + 0.5 * replies - 1.25 * negative
    return effective / max(1.0, float(views))


def audience_performance_score(row: Any, baseline: float) -> float:
    views = _row_int(row, "views")
    if views <= 0:
        return 0.0
    raw = audience_raw_rate(row)
    denom = max(0.003, abs(float(baseline)))
    relative = max(-1.0, min(2.0, (raw - float(baseline)) / denom))
    confidence = min(1.0, math.sqrt(views / 100.0))
    return relative * confidence


@dataclass(frozen=True, slots=True)
class TopicAssessment:
    score: float = 0.0
    admin_score: float = 0.0
    audience_score: float = 0.0
    fit_adjustment: int = 0
    hard_suppress: bool = False
    matched_article_id: int = 0
    matched_similarity: float = 0.0
    rated_posts: int = 0


class LearningEngine:
    """Adaptive editorial memory only. It never talks to Telegram and never owns UI state."""

    def __init__(self, store: V2Store):
        self.store = store
        self.feedback = FeedbackService(store)

    def topic_assessment(self, channel_id: int, article: Any) -> TopicAssessment:
        try:
            rows = self.feedback.feedback_rows(channel_id, days=FEEDBACK_WINDOW_DAYS, limit=180)
        except sqlite3.OperationalError:  # type: ignore[name-defined]
            return TopicAssessment()
        if not rows:
            return TopicAssessment()
        query = _candidate_text(article)
        now = datetime.now(timezone.utc)
        rates = [audience_raw_rate(row) for row in rows if _row_int(row, "views") >= 25]
        baseline = statistics.median(rates) if rates else 0.0
        admin_score = 0.0
        audience_score = 0.0
        hard = False
        matched_id = 0
        matched_similarity = 0.0
        best_admin_contribution = 0.0
        source_scores: list[float] = []
        candidate_source_id = str(_v(article, "source_id", "") or "")

        for row in rows:
            published = _parse_dt(str(_v(row, "published_at", "") or _v(row, "checked_at", "")))
            age_hours = 24.0 * FEEDBACK_WINDOW_DAYS
            if published is not None:
                age_hours = max(0.0, (now - published).total_seconds() / 3600.0)
            if age_hours > 24.0 * FEEDBACK_WINDOW_DAYS:
                continue
            sim, shared = similarity_parts(query, _feedback_text(row))
            if sim <= 0:
                continue
            admin = topic_feedback_signal(row)
            if admin:
                decay = 0.5 ** (age_hours / 72.0)
                contribution = sim * decay * admin
                admin_score += contribution
                if abs(contribution) > best_admin_contribution:
                    best_admin_contribution = abs(contribution)
                    matched_id = int(_v(row, "article_id", 0) or 0)
                    matched_similarity = sim
                if admin < 0 and _row_int(row, "dislikes") > _row_int(row, "likes") and shared >= 4:
                    threshold = 0.18 if age_hours <= 24 else 0.24 if age_hours <= 72 else 0.32
                    if sim >= threshold:
                        hard = True
                        matched_id = int(_v(row, "article_id", 0) or 0)
                        matched_similarity = sim
            perf = audience_performance_score(row, baseline)
            if perf:
                decay = 0.5 ** (age_hours / 96.0)
                audience_score += sim * decay * perf * AUDIENCE_TOPIC_WEIGHT
                if candidate_source_id and str(_v(row, "source_id", "") or "") == candidate_source_id:
                    source_scores.append(perf * decay)

        if source_scores:
            source_bonus = max(-SOURCE_AUDIENCE_WEIGHT, min(SOURCE_AUDIENCE_WEIGHT * 2, statistics.mean(source_scores) * SOURCE_AUDIENCE_WEIGHT))
            audience_score += source_bonus
        score = admin_score + audience_score
        adjustment = int(round(max(-12.0, min(12.0, score * 4.0))))
        return TopicAssessment(
            score=score, admin_score=admin_score, audience_score=audience_score,
            fit_adjustment=adjustment, hard_suppress=hard,
            matched_article_id=matched_id, matched_similarity=matched_similarity,
            rated_posts=len(rows),
        )

    def topic_memory_block(self, channel_id: int, article: Any) -> str:
        try:
            rows = self.feedback.feedback_rows(channel_id, days=FEEDBACK_WINDOW_DAYS, limit=180)
        except Exception:
            return ""
        if not rows:
            return ""
        query = _candidate_text(article)
        rates = [audience_raw_rate(row) for row in rows if _row_int(row, "views") >= 25]
        baseline = statistics.median(rates) if rates else 0.0
        ranked: list[tuple[float, str]] = []
        for row in rows:
            sim, shared = similarity_parts(query, _feedback_text(row))
            if sim <= 0.08 or shared < 2:
                continue
            admin = topic_feedback_signal(row)
            audience = audience_performance_score(row, baseline)
            if admin == 0 and abs(audience) < 0.2:
                continue
            title = " ".join(str(_v(row, "title", "") or "").split())[:180]
            label = []
            if admin > 0:
                label.append(f"ADMIN +{admin:.0f}")
            elif admin < 0:
                label.append(f"ADMIN {admin:.0f}")
            if audience >= 0.2:
                label.append("AUDIENCE +")
            elif audience <= -0.2:
                label.append("AUDIENCE -")
            ranked.append((abs(admin) * 2.0 + abs(audience) + sim, f"- {'; '.join(label)} · схожість {sim:.2f} · {title}"))
        ranked.sort(key=lambda item: -item[0])
        lines = [item[1] for item in ranked[:5]]
        if not lines:
            return ""
        return (
            "АДАПТИВНА ПАМ'ЯТЬ ТЕМ ЗА 7 ДНІВ. Це м'який пріоритет, а не джерело фактів. "
            "Адмінські 👍/👎 сильніші за аудиторію; 🔥 тут ігнорується. Аудиторія нормалізована на перегляди.\n"
            + "\n".join(lines)
        )

    def style_memory_block(self, channel_id: int, article: Any) -> str:
        try:
            rows = self.feedback.feedback_rows(channel_id, days=STYLE_WINDOW_DAYS, limit=180)
        except Exception:
            return ""
        if not rows:
            return ""
        query = _candidate_text(article)
        now = datetime.now(timezone.utc)
        ranked: list[tuple[float, Any]] = []
        for row in rows:
            fire = style_feedback_signal(row)
            text = " ".join(str(_v(row, "final_text", "") or "").split())
            if fire <= 0 or not text:
                continue
            published = _parse_dt(str(_v(row, "published_at", "") or _v(row, "checked_at", "")))
            age_hours = 24.0 * STYLE_WINDOW_DAYS
            if published is not None:
                age_hours = max(0.0, (now - published).total_seconds() / 3600.0)
            if age_hours > 24.0 * STYLE_WINDOW_DAYS:
                continue
            sim, _ = similarity_parts(query, _feedback_text(row))
            decay = 0.5 ** (age_hours / 96.0)
            rank = (0.45 + sim) * decay * (1.0 + 0.35 * min(3.0, fire - 1.0))
            ranked.append((rank, row))
        ranked.sort(key=lambda item: -item[0])
        if not ranked:
            return ""
        chunks = [
            "СТИЛЬОВА ПАМ'ЯТЬ КАНАЛУ ЗА 7 ДНІВ.",
            "Тут тільки тексти, які адміністратори позначили 🔥. Наслідуй ритм, щільність, абзаци та спосіб входу в тему, але не копіюй фрази. Ці приклади НЕ є джерелом фактів.",
        ]
        for index, (_rank, row) in enumerate(ranked[:MAX_STYLE_EXAMPLES], start=1):
            text = " ".join(str(_v(row, "final_text", "") or "").split())[:760]
            chunks.append(f"🔥{index}: {text}")
        return "\n".join(chunks)

    def summary(self, channel_id: int) -> dict[str, Any]:
        try:
            rows = self.feedback.feedback_rows(channel_id, days=FEEDBACK_WINDOW_DAYS, limit=300)
            stats = self.feedback.stats(channel_id)
        except Exception:
            return {"topic_positive": 0, "topic_negative": 0, "style_examples": 0, "audience_examples": 0, "last_checked": ""}
        return {
            "topic_positive": sum(1 for r in rows if topic_feedback_signal(r) > 0),
            "topic_negative": sum(1 for r in rows if topic_feedback_signal(r) < 0),
            "style_examples": sum(1 for r in rows if style_feedback_signal(r) > 0),
            "audience_examples": sum(1 for r in rows if _row_int(r, "views") > 0 and (_row_int(r, "audience_total") > 0 or _row_int(r, "forwards") > 0 or _row_int(r, "replies") > 0)),
            "last_checked": str(stats.get("last_checked") or ""),
        }
