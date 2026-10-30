"""v2.2.58: read-only commercial editorial feed mix and headline-fatigue context.

Never convert a thematic resemblance into a duplicate, rejection or quota.
Real published posts only, no source/operator configuration changes or extra AI calls.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
import re
from typing import Any

from .commercial_diversity_257 import commercial_published_share_7d


_THEME_RULES = (
    ("pop_culture", re.compile(r"(?i)\b(?:pokemon|pok[eé]mon|lego|halloween|harry potter|star wars|anime|comic.con|super mario)\b|покемон|гелловін|хелловін|гаррі поттер|комікс")),
    ("campaign_stunt", re.compile(r"(?i)\b(?:campaign|advertis(?:ing|ement|er)?|brand stunt|viral stunt|pr stunt|activation|billboard|commercial film|stop.motion)\b|рекламн|кампані|бренд.акці|вірусн. реклам|рекламн. трюк")),
    ("tiny_living", re.compile(r"(?i)\b(?:tiny (?:house|home|cabin)|micro.home|mini.house|prefab house|modular home|tiny living|compact cabin)\b|мінібудин|крихітн. будин|модульн. будин|компактн. будин|міні.саун")),
    ("consumer_gadgets", re.compile(r"(?i)\b(?:gadgets?|smartphones?|smartwatches?|headphones?|earbuds?|smart glasses|wearables?|power bank|3d.print(?:er|ing)?)\b|гаджет|смартфон|навушник|розумн. окуляр|3d.друк|3д.друк")),
    ("furniture_objects", re.compile(r"(?i)\b(?:furniture|chairs?|armchairs?|sofas?|tables?|lamps?|vases?|shelves?|designer cup|coffee mug)\b|мебл|диван|стілець|крісел|крісл|світильник|ваза|дизайнерськ. склян")),
    ("ai_robotics", re.compile(r"(?i)\b(?:robots?|robotic|artificial intelligence|machine learning|ai.powered|ai.generated)\b|робот|штучн. інтелект|нейромереж")),
    ("architecture_spaces", re.compile(r"(?i)\b(?:architecture|architectural|pavilion|skyscraper|building design|public space)\b|архітектур|павільйон|хмарочос|громадськ. простір")),
    ("human_culture", re.compile(r"(?i)\b(?:book rave|consumer behavior|human behavior|street art|social experiment|lost cat|missing pets?)\b|поведінк. людей|соціальн. експеримент|вуличн. мистецтв|загублен. кот")),
)
_STOP = frozenset(
    "the and for with from into new that this your their about after before makes made "
    "what when where how has have will are was were you they more less than its "
    "для який яка яке вони вона його його з цього цієї цей новий нова нове через "
    "та про під над або вже ще без від до на у із зі що як де після".split()
)


def _get(row: Any, key: str, default: Any = "") -> Any:
    try:
        value = row[key]
    except (KeyError, IndexError, TypeError):
        value = getattr(row, key, default)
    return default if value is None else value


def commercial_theme_258(row: Any) -> str:
    """Conservative lexical group, NOT an asserted AI classification."""
    title = str(_get(row, "title") or "")
    for label, pattern in _THEME_RULES:
        if pattern.search(title):
            return label
    # Avoid guessing from a long generated article: short context only.
    final = str(_get(row, "final_text") or "")[:200]
    for label, pattern in _THEME_RULES:
        if pattern.search(final):
            return label
    return "other"


def _title_tokens(title: str) -> set[str]:
    return {word for word in re.findall(r"(?u)\b[^\W\d_]{3,}\b", title.casefold())
            if word not in _STOP}


def _headline_echo(left: Any, right: Any) -> bool:
    a = _title_tokens(str(_get(left, "title") or ""))
    b = _title_tokens(str(_get(right, "title") or ""))
    if min(len(a), len(b)) < 4:
        return False
    intersection = len(a & b)
    return intersection >= 4 and intersection / max(1, min(len(a), len(b))) >= 0.65


def _published_rows(store: Any, channel_id: int, *, limit: int = 160) -> list[Any]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat(timespec="seconds")
    with store.connect() as con:
        return list(con.execute(
            """SELECT a.id,a.source_id,a.title,a.final_text,a.published_at,
                      s.name AS source_name
               FROM articles a JOIN sources s ON s.id=a.source_id
               WHERE a.channel_id=? AND a.stage='PUBLISHED' AND a.published_at<>''
                 AND datetime(a.published_at)>=datetime(?)
               ORDER BY datetime(a.published_at) DESC,a.id DESC LIMIT ?""",
            (int(channel_id), cutoff, max(1, min(160, int(limit)))),
        ).fetchall())


def commercial_topic_mix_7d_258(store: Any, channel_id: int) -> dict[str, Any]:
    """Supervisor report from published feed; 160-post cap is disclosed."""
    rows = _published_rows(store, channel_id)
    themes = [commercial_theme_258(row) for row in rows]
    counts = Counter(themes)
    last_six = themes[:6]
    run = 0
    if themes and themes[0] != "other":
        for label in themes:
            if label != themes[0]:
                break
            run += 1
    recent_echoes = sum(
        1 for i in range(min(12, len(rows)))
        for j in range(i + 1, min(12, len(rows)))
        if _headline_echo(rows[i], rows[j])
    )
    source_share = commercial_published_share_7d(store, channel_id)
    names = {int(_get(row, "source_id", 0)): str(_get(row, "source_name"))
             for row in rows}
    top_sources = [
        {"source_id": sid, "name": names.get(sid, str(sid)),
         "posts_7d": n, "share": round(n / source_share["total_posts"], 4)}
        for sid, n in sorted(source_share["counts"].items(),
                             key=lambda item: (-item[1], item[0]))[:5]
    ] if source_share["total_posts"] else []
    return {
        "mode": "advisory_only", "window_days": 7,
        "published_sample_size": len(rows), "sample_limit": 160,
        "sample_limit_reached": len(rows) == 160,
        "category_method": "conservative_headline_keywords_with_short_text_fallback",
        "theme_counts": dict(sorted(counts.items())),
        "recent_six_themes": last_six,
        "consecutive_theme_run": run,
        "similar_headline_pairs_last_12": recent_echoes,
        "source_published_total_7d": source_share["total_posts"],
        "top_sources": top_sources,
        "no_rejection_or_quota": True,
        "no_operator_data_mutation": True,
    }


def commercial_topic_advisory_258(store: Any, channel_id: int, article: Any) -> str:
    """Small context addition to an EXISTING selector call, never a veto."""
    rows = _published_rows(store, channel_id, limit=12)
    if not rows:
        return ""
    theme = commercial_theme_258(article)
    last_six = rows[:6]
    similar = sum(commercial_theme_258(row) == theme for row in last_six) if theme != "other" else 0
    echoed = [int(_get(row, "id", 0) or 0) for row in rows
              if _headline_echo(article, row)]
    if similar < 2 and not echoed:
        return ""
    pieces = ["КОНТЕКСТ ОПУБЛІКОВАНОЇ СТРІЧКИ v2.2.58 (лише порада, НЕ заборона):"]
    if similar >= 2:
        pieces.append(f"Лексична тема «{theme}» зустрілася {similar} раз(и) серед останніх {len(last_six)} дописів.")
    if echoed:
        pieces.append(f"Подібні заголовки раніше: {', '.join('#'+str(i) for i in echoed[:3])}.")
    pieces.append(
        "Перевір, чи в SOURCE є НОВИЙ конкретний сюжет для широкої аудиторії. "
        "Схожа тема/заголовок НЕ доводять дубль. Не відхиляй сильну незалежну історію "
        "заради різноманітності; не вигадуй відмінностей і не послаблюй стандартні критерії."
    )
    return " ".join(pieces)


__all__ = [
    "commercial_theme_258", "commercial_topic_mix_7d_258",
    "commercial_topic_advisory_258",
]
