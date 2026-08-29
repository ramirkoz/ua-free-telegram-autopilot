from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from . import rc51_feedback as rc51

_INSTALLED = False
TOPIC_LIKE_WEIGHT = 1.0
TOPIC_DISLIKE_WEIGHT = -2.0
STYLE_FIRE_WEIGHT = 1.0
STYLE_WINDOW_DAYS = 7
MAX_STYLE_EXAMPLES = 5


def _row_int(row: Mapping[str, Any] | Any, key: str) -> int:
    try:
        value = row[key]
    except Exception:
        value = getattr(row, key, 0)
    try:
        return max(0, int(value or 0))
    except Exception:
        return 0


def topic_feedback_signal(row: Mapping[str, Any] | Any) -> float:
    """Topic preference only: 👍 raises affinity, 👎 lowers/suppresses it.

    🔥 is deliberately ignored here. It means "well written", not "more of this topic".
    """
    return (
        _row_int(row, "likes") * TOPIC_LIKE_WEIGHT
        + _row_int(row, "dislikes") * TOPIC_DISLIKE_WEIGHT
    )


def style_feedback_signal(row: Mapping[str, Any] | Any) -> float:
    """Writing-style preference only: 🔥 marks a published post as a style example."""
    return _row_int(row, "fires") * STYLE_FIRE_WEIGHT


def _age_hours(row: Mapping[str, Any] | Any) -> float:
    value = rc51._row_value(row, "published_at") or rc51._row_value(row, "checked_at")
    dt = rc51._parse_dt(value)
    if dt is None:
        return 24.0 * STYLE_WINDOW_DAYS
    return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0)


def style_memory_block(channel: Any, article: Any, *, purpose: str = "writing") -> str:
    """Return only 🔥-approved Telegram copy as writing references.

    Topic reactions never enter this block. This lets a post be simultaneously
    👎 for topic and 🔥 for writing quality, or 👍 for topic without teaching its prose.
    """
    if str(purpose or "writing") != "writing":
        return ""
    db = rc51._ACTIVE_DB
    if db is None:
        return ""
    try:
        rows = db.rc51_feedback_rows(
            int(getattr(channel, "id", 0) or 0),
            days=STYLE_WINDOW_DAYS,
            limit=rc51.MAX_FEEDBACK_ROWS,
        )
    except Exception:
        return ""
    if not rows:
        return ""

    query = rc51._candidate_text(article)
    ranked: list[tuple[float, dict[str, Any]]] = []
    for row in rows:
        fire = style_feedback_signal(row)
        if fire <= 0:
            continue
        age_hours = _age_hours(row)
        if age_hours > 24.0 * STYLE_WINDOW_DAYS:
            continue
        sim, _shared = rc51.similarity_parts(query, rc51._feedback_text(row))
        decay = 0.5 ** (age_hours / 96.0)
        rank = (0.45 + sim) * decay * (1.0 + 0.35 * min(3.0, fire - 1.0))
        ranked.append((rank, row))

    ranked.sort(key=lambda item: -item[0])
    ranked = ranked[:MAX_STYLE_EXAMPLES]
    if not ranked:
        return ""

    chunks = [
        "СТИЛЬОВА ПАМ'ЯТЬ КАНАЛУ ЗА ОСТАННІ 7 ДНІВ.",
        "Тут ТІЛЬКИ пости з 🔥. 🔥 означає: текст написаний добре. Він НЕ означає, що тема цікава.",
        "👍 і 👎 у стильовій пам'яті ігноруються. Вони впливають тільки на відбір тем.",
        "Наслідуй ритм, щільність, довжину абзаців, спосіб входу в історію та подачу деталей, але не копіюй формулювання.",
        "Ці приклади НЕ є джерелом фактів. Факти поточного поста бери тільки з SOURCE.",
        "\n🔥 ПРИКЛАДИ ВДАЛОЇ ПОДАЧІ:",
    ]
    for index, (_rank, row) in enumerate(ranked, start=1):
        text = " ".join(str(row.get("teaser_text") or "").split())[:900]
        if not text:
            text = " ".join(str(row.get("title") or "").split())[:900]
        chunks.append(f"🔥{index} ({_row_int(row, 'fires')}): {text}")
    return "\n".join(chunks)


def install_rc52_feedback() -> None:
    """Split RC51's blended reaction signal into independent topic/style channels."""
    global _INSTALLED
    if _INSTALLED:
        return

    from . import production_pipeline as production
    from . import rc40_policy as rc40
    from . import rc48_learning as rc48
    from . import service as service_module

    rc51._feedback_signal = topic_feedback_signal
    rc51.feedback_memory_block = style_memory_block
    rc48._format_memory_block = style_memory_block
    rc40.build_russian_editorial_prompt = rc51.build_ru_feedback_editor_prompt
    rc40.build_ukrainian_bridge_prompt = rc51.build_ua_feedback_writer_prompt
    production.POST_FORMAT_PREFIX = "telegram-post-v33:"
    service_module.POST_FORMAT_PREFIX = "telegram-post-v33:"

    _INSTALLED = True
