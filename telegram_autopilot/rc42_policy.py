from __future__ import annotations

import json
import logging
import math
import re
from collections import Counter
from typing import Any, Iterable, Mapping

from .ai_router import AIRouterError, run_ai
from .models import Decision

LOG = logging.getLogger("telegram_autopilot.rc42")
_INSTALLED = False

_OTHER = "__OTHER__"


def _row_value(row: Mapping[str, Any] | Any, key: str, default: str = "") -> str:
    try:
        value = row[key]
    except Exception:
        return default
    return default if value is None else str(value)


def _story(row: Mapping[str, Any] | Any) -> str:
    return "\n".join(
        part
        for part in (
            _row_value(row, "title"),
            _row_value(row, "teaser_text"),
            _row_value(row, "event_summary"),
            _row_value(row, "full_article_uk"),
            _row_value(row, "raw_text")[:5000],
        )
        if part
    )


def parse_editorial_weights(channel: Any) -> list[dict[str, Any]]:
    """Return the operator-defined per-channel editorial categories.

    RC42 deliberately does not ship any technology/security/AI percentages.  A
    channel with no configured weights has no topic-balance gate at all.
    """
    raw = str(getattr(channel, "editorial_weights_json", "") or "").strip()
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except Exception:
        return []
    if not isinstance(value, list):
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        name = " ".join(str(item.get("name") or "").split()).strip()
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        try:
            weight = float(item.get("weight", 0) or 0)
        except (TypeError, ValueError):
            continue
        weight = max(0.0, min(100.0, weight))
        out.append({"name": name[:120], "weight": weight})
        seen.add(key)
    return out


def serialize_editorial_weights(items: Iterable[Mapping[str, Any]]) -> str:
    clean: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        name = " ".join(str(item.get("name") or "").split()).strip()
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        try:
            weight = float(item.get("weight", 0) or 0)
        except (TypeError, ValueError):
            continue
        clean.append({"name": name[:120], "weight": round(max(0.0, min(100.0, weight)), 3)})
        seen.add(key)
    return json.dumps(clean, ensure_ascii=False, separators=(",", ":"))


_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яІіЇїЄєҐґ0-9]+")
_STOP = {
    "and", "the", "for", "with", "news", "other", "та", "і", "й", "або", "для", "про",
    "новини", "тема", "категорія",
}


def _name_tokens(name: str) -> set[str]:
    return {
        token.casefold()
        for token in _TOKEN_RE.findall(str(name or ""))
        if len(token) >= 2 and token.casefold() not in _STOP
    }


def lexical_category(article: Mapping[str, Any] | Any, categories: list[dict[str, Any]]) -> str:
    """Cheap first pass.  AI is used only when category names are not explicit in SOURCE."""
    title = f" {_row_value(article, 'title').casefold()} "
    body = f" {_story(article).casefold()} "
    scored: list[tuple[int, str]] = []
    for item in categories:
        name = str(item["name"])
        tokens = _name_tokens(name)
        if not tokens:
            continue
        score = 0
        for token in tokens:
            if re.search(rf"(?<!\w){re.escape(token)}(?!\w)", title, re.I):
                score += 4
            elif re.search(rf"(?<!\w){re.escape(token)}(?!\w)", body, re.I):
                score += 1
        if score:
            scored.append((score, name))
    if not scored:
        return ""
    scored.sort(reverse=True)
    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        return ""
    return scored[0][1]


def _validated_category(raw: str, categories: list[dict[str, Any]]) -> str:
    text = " ".join(str(raw or "").strip().strip("`\"'").split())
    allowed = {str(item["name"]).casefold(): str(item["name"]) for item in categories}
    if text.casefold() == _OTHER.casefold():
        return _OTHER
    if text.casefold() not in allowed:
        raise ValueError("classification must return exactly one configured category or __OTHER__")
    return allowed[text.casefold()]


def classify_category(channel: Any, article: Mapping[str, Any] | Any, categories: list[dict[str, Any]]) -> str:
    if not categories:
        return ""
    lexical = lexical_category(article, categories)
    if lexical:
        return lexical

    names = "\n".join(f"- {item['name']}" for item in categories)
    profile = " ".join(str(getattr(channel, "editorial_profile", "") or "").split())[:1600]
    prompt = f"""Classify ONE news item into ONE operator-defined editorial category.
The category names are semantic labels, not literal keyword requirements. Use the channel profile as context.
Return EXACTLY one category name from the list, with no punctuation or explanation.
If none fits, return exactly {_OTHER}.

CHANNEL PROFILE:
{profile or '(not specified)'}

CATEGORIES:
{names}

TITLE:
{_row_value(article, 'title')[:800]}

SOURCE EXCERPT:
{_row_value(article, 'raw_text')[:3000]}
"""

    def validator(value: str) -> None:
        _validated_category(value, categories)

    try:
        result = run_ai(
            prompt,
            validator=validator,
            max_output_tokens=64,
            local_prompt=prompt,
            local_max_output_tokens=64,
            cloud_timeout_seconds=12,
            local_timeout_seconds=18,
            task_timeout_seconds=30,
            local_repair=False,
            skip_providers={"codex"},
            suppress_provider_on_quota=False,
            allowed_providers={"gemini", "groq", "nvidia", "cloudflare", "local"},
        )
        category = _validated_category(result.text, categories)
        return "" if category == _OTHER else category
    except AIRouterError as exc:
        LOG.info("RC42 category classifier unavailable; balance skipped for article_id=%s: %s", _row_value(article, "id", "?"), exc)
        return ""
    except Exception as exc:
        LOG.info("RC42 category classifier rejected output; balance skipped for article_id=%s: %s", _row_value(article, "id", "?"), exc)
        return ""


def balance_reject_reason(
    channel: Any,
    article: Mapping[str, Any] | Any,
    recent: Iterable[Mapping[str, Any] | Any],
    *,
    category: str | None = None,
) -> tuple[str, str]:
    categories = parse_editorial_weights(channel)
    if not categories:
        return "", ""
    category = str(category or "").strip() or classify_category(channel, article, categories)
    if not category:
        return "", ""

    weights = {str(item["name"]): float(item["weight"]) for item in categories}
    lookup = {name.casefold(): name for name in weights}
    canonical = lookup.get(category.casefold())
    if canonical is None:
        return "", ""
    category = canonical
    weight = weights[category]
    positive_total = sum(value for value in weights.values() if value > 0)

    if weight <= 0:
        return f"EDITORIAL_WEIGHT_RC42_SKIP: категорія «{category}» має вагу 0 для каналу «{getattr(channel, 'name', '')}».", category
    if positive_total <= 0:
        return "", category

    recent_categories: list[str] = []
    for row in list(recent)[:24]:
        value = _row_value(row, "editorial_category").strip()
        if not value:
            continue
        current = lookup.get(value.casefold())
        if current is not None:
            recent_categories.append(current)
    if len(recent_categories) < 5:
        return "", category

    sample = recent_categories[:20]
    count = Counter(sample)[category]
    target = weight / positive_total
    projected = (count + 1) / (len(sample) + 1)
    # One-post tolerance keeps small rolling windows from oscillating around a
    # percentage boundary.  The configured weights remain targets, not quotas.
    tolerance = max(0.06, 1.0 / (len(sample) + 1))
    if projected > target + tolerance and count > 0:
        normalized_pct = target * 100.0
        return (
            f"EDITORIAL_WEIGHT_RC42_SKIP: «{category}» уже займає {count}/{len(sample)} відомих "
            f"категорій; цільова вага каналу ≈{normalized_pct:.1f}%. Наступний слот віддаємо "
            "категорії, що недобирає свою редакційну вагу.",
            category,
        )
    return "", category


def _generic_newsworthiness(article: Mapping[str, Any] | Any) -> str:
    """Only universal junk filters. Domain policy now belongs to each channel."""
    title = f" {_row_value(article, 'title').casefold()} "
    body = f" {_row_value(article, 'raw_text')[:5000].casefold()} "
    hard = (
        "buying guide", "gift guide", "our picks", "best accessories", "coupon roundup",
        "shopping guide", "affiliate roundup",
    )
    if any(signal in title for signal in hard):
        return "NEWSWORTHINESS_RC42_SKIP: купівельна/affiliate-добірка не є самостійною редакційною новиною."
    if "sponsored content" in body or "affiliate commission" in body:
        return "NEWSWORTHINESS_RC42_SKIP: рекламний або affiliate-матеріал."
    return ""


def install_rc42_policy() -> None:
    """RC42: per-channel operator-defined editorial profiles and weights."""
    global _INSTALLED
    if _INSTALLED:
        return

    from . import production_pipeline as production_module
    from . import rc37_policy as rc37_module
    from . import rc38_policy as rc38_module
    from . import service as service_module
    from .database import Database

    # Additive SQLite compatibility. Existing Data folders remain valid.
    original_init = Database._init
    original_update_article = Database.update_article

    def init_with_rc42(self) -> None:
        original_init(self)
        with self.connect() as con:
            self._ensure_column(con, "channels", "editorial_weights_json", "TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column(con, "articles", "editorial_category", "TEXT NOT NULL DEFAULT ''")

    def update_article_rc42(self, article_id: int, **fields: object) -> None:
        category = fields.pop("editorial_category", None)
        original_update_article(self, article_id, **fields)
        if category is not None:
            with self.connect() as con:
                con.execute("UPDATE articles SET editorial_category=? WHERE id=?", (str(category)[:120], article_id))

    def set_channel_editorial_weights(self, channel_id: int, items: Iterable[Mapping[str, Any]]) -> None:
        payload = serialize_editorial_weights(items)
        with self.connect() as con:
            con.execute(
                "UPDATE channels SET editorial_weights_json=?,updated_at=datetime('now') WHERE id=?",
                (payload, int(channel_id)),
            )

    def recent_published_rc42(self, channel_id: int, hours: int, limit: int = 30):
        with self.connect() as con:
            return con.execute(
                """SELECT id,title,event_key,event_summary,headline_uk,teaser_text,full_article_uk,
                          published_at,url,editorial_category
                   FROM articles
                   WHERE channel_id=? AND status='published' AND datetime(published_at) >= datetime('now', ?)
                   ORDER BY published_at DESC LIMIT ?""",
                (channel_id, f"-{max(1, int(hours))} hours", limit),
            ).fetchall()

    Database._init = init_with_rc42
    Database.update_article = update_article_rc42
    Database.set_channel_editorial_weights = set_channel_editorial_weights
    Database.recent_published = recent_published_rc42

    # Remove RC41's global CTRL+UA policy.  RC40 still calls these functions, so
    # they must be neutral/channel-agnostic before the per-channel wrapper runs.
    rc37_module.newsworthiness_reject_reason = _generic_newsworthiness
    rc38_module.topic_balance_reject_reason = lambda article, recent: ""
    production_module._deterministic_reject_reason = _generic_newsworthiness

    original_decide = production_module.decide

    def decide(channel, article, recent, *, hard_limit=production_module.MEDIA_POST_HARD_LIMIT, format_marker=None):
        categories = parse_editorial_weights(channel)
        category = ""
        if categories:
            category = classify_category(channel, article, categories)
            reason, category = balance_reject_reason(channel, article, recent, category=category)
            article_id = _row_value(article, "id", "")
            if article_id and category:
                try:
                    Database().update_article(int(article_id), editorial_category=category)
                except Exception as exc:
                    LOG.debug("RC42 category persistence skipped article_id=%s: %s", article_id, exc)
            if reason:
                return Decision(
                    decision="reject", duplicate_of=None, reason=reason,
                    event_key="channel-editorial-weight-v1", event_summary=_row_value(article, "title")[:1000],
                    headline_uk="", telegram_teaser="", full_article_uk="", media_captions_uk={},
                    confidence=0.99, provider="local-rule", model="rc42-channel-weights",
                )

        result = original_decide(
            channel, article, recent, hard_limit=hard_limit, format_marker=format_marker
        )
        return result

    marker = "telegram-post-v27:"
    production_module.POST_FORMAT_PREFIX = marker
    service_module.POST_FORMAT_PREFIX = marker
    production_module.decide = decide
    service_module.decide = decide
    _INSTALLED = True
