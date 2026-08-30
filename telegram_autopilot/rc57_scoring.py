from __future__ import annotations

import logging
import statistics
from datetime import datetime, timezone
from typing import Any

from .rc57_feedback_model import (
    AUDIENCE_TOPIC_WEIGHT,
    FEEDBACK_WINDOW_DAYS,
    SOURCE_AUDIENCE_WEIGHT,
    audience_performance_score,
    audience_raw_rate,
    row_int,
    row_value,
)

LOG = logging.getLogger("telegram_autopilot.rc57")
_BASE_SCORE = None


def combined_score_against_feedback(article: Any, feedback_rows: list[Any]):
    from . import rc51_feedback as rc51
    base_fn = _BASE_SCORE or rc51.score_against_feedback
    base = base_fn(article, feedback_rows)

    rates = [audience_raw_rate(row) for row in feedback_rows if row_int(row, "views") >= 25]
    baseline = statistics.median(rates) if rates else 0.0
    query = rc51._candidate_text(article)
    now = datetime.now(timezone.utc)
    audience_positive = 0.0
    audience_negative = 0.0
    candidate_source_id = str(row_value(article, "source_id", "") or "")
    source_scores: list[float] = []

    for row in feedback_rows:
        perf = audience_performance_score(row, baseline)
        if perf == 0:
            continue
        published = rc51._parse_dt(str(row_value(row, "published_at", "") or row_value(row, "checked_at", "")))
        age_hours = 24.0 * FEEDBACK_WINDOW_DAYS
        if published is not None:
            age_hours = max(0.0, (now - published).total_seconds() / 3600.0)
        if age_hours > 24.0 * FEEDBACK_WINDOW_DAYS:
            continue
        decay = 0.5 ** (age_hours / 96.0)
        sim, _shared = rc51.similarity_parts(query, rc51._feedback_text(row))
        contribution = sim * decay * perf * AUDIENCE_TOPIC_WEIGHT
        if contribution >= 0:
            audience_positive += contribution
        else:
            audience_negative += -contribution
        if candidate_source_id and str(row_value(row, "source_id", "") or "") == candidate_source_id:
            source_scores.append(perf * decay)

    source_bonus = 0.0
    if source_scores:
        source_bonus = max(
            -SOURCE_AUDIENCE_WEIGHT,
            min(SOURCE_AUDIENCE_WEIGHT * 2, statistics.mean(source_scores) * SOURCE_AUDIENCE_WEIGHT),
        )
        if source_bonus >= 0:
            audience_positive += source_bonus
        else:
            audience_negative += -source_bonus

    result = rc51.FeedbackScore(
        score=float(base.score) + audience_positive - audience_negative,
        positive=float(base.positive) + audience_positive,
        negative=float(base.negative) + audience_negative,
        hard_suppress=bool(base.hard_suppress),
        matched_article_id=int(base.matched_article_id),
        matched_similarity=float(base.matched_similarity),
        matched_age_hours=float(base.matched_age_hours),
        rated_posts=max(int(base.rated_posts), len([r for r in feedback_rows if row_int(r, "audience_total") > 0])),
    )
    LOG.debug(
        "combined feedback score=%.3f editor=%.3f audience=%.3f source=%.3f baseline=%.5f",
        result.score, float(base.score), audience_positive - audience_negative - source_bonus, source_bonus, baseline,
    )
    return result


def install_scoring_patch() -> None:
    global _BASE_SCORE
    from . import rc51_feedback
    if rc51_feedback.score_against_feedback is combined_score_against_feedback:
        return
    _BASE_SCORE = rc51_feedback.score_against_feedback
    rc51_feedback.score_against_feedback = combined_score_against_feedback
