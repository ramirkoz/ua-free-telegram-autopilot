from __future__ import annotations

import difflib
import json
import logging
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from .ai_router import AIRouterError, run_ai
from .rc42_policy import parse_editorial_weights

LOG = logging.getLogger("telegram_autopilot.rc46")
_INSTALLED = False
_OTHER = "__OTHER__"
_UNCLASSIFIED = "__UNCLASSIFIED__"


def _row_value(row: Mapping[str, Any] | Any, key: str, default: str = "") -> str:
    try:
        value = row[key]
    except Exception:
        return default
    return default if value is None else str(value)


def _category_key(value: str) -> str:
    text = str(value or "").casefold()
    text = text.replace("&", " and ").replace("+", " and ")
    text = re.sub(r"[/_|,:;–—-]+", " ", text)
    text = re.sub(r"\band\b", " and ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _clean_classifier_output(raw: str) -> str:
    value = str(raw or "").strip()
    value = re.sub(r"(?is)<think>.*?</think>|<analysis>.*?</analysis>", "", value).strip()
    value = re.sub(r"^```(?:json|text|markdown)?\s*|\s*```$", "", value, flags=re.I).strip()
    if value.startswith("{"):
        try:
            obj = json.loads(value)
        except Exception:
            obj = None
        if isinstance(obj, dict):
            value = str(obj.get("category") or obj.get("label") or obj.get("result") or "").strip()
    value = re.sub(r"(?i)^\s*(?:category|категорія|категория|label)\s*[:\-–—]\s*", "", value).strip()
    return " ".join(value.strip("`*# \t\r\n\"'").split())


def extract_category_rc46(raw: str, categories: list[dict[str, Any]]) -> str:
    """Tolerant but high-confidence parser for operator-defined category labels.

    RC45 rejected perfectly reasonable provider answers such as
    ``Science and Health`` for the configured label ``Science & Health``. RC46
    normalizes punctuation/connectors and allows a single unambiguous fuzzy hit.
    """
    compact = _clean_classifier_output(raw)
    low = compact.casefold()
    if low in {_OTHER.casefold(), "other", "none", "out of scope", "out-of-scope"}:
        return _OTHER
    if re.search(r"\b(?:other|none|out[- ]of[- ]scope)\b", low, re.I):
        return _OTHER

    by_key: dict[str, list[str]] = {}
    for item in categories:
        canonical = str(item["name"])
        by_key.setdefault(_category_key(canonical), []).append(canonical)

    key = _category_key(compact)
    exact = by_key.get(key, [])
    if len(exact) == 1:
        return exact[0]

    # Providers sometimes add one harmless word around the actual category.
    contained: list[str] = []
    padded = f" {key} "
    for normalized, canonicals in by_key.items():
        if len(canonicals) == 1 and normalized and f" {normalized} " in padded:
            contained.append(canonicals[0])
    contained = list(dict.fromkeys(contained))
    if len(contained) == 1:
        return contained[0]

    scored: list[tuple[float, str]] = []
    for normalized, canonicals in by_key.items():
        if len(canonicals) != 1 or not normalized or not key:
            continue
        ratio = difflib.SequenceMatcher(None, key, normalized).ratio()
        scored.append((ratio, canonicals[0]))
    scored.sort(reverse=True)
    if scored:
        best_score, best_name = scored[0]
        second = scored[1][0] if len(scored) > 1 else 0.0
        if best_score >= 0.84 and best_score - second >= 0.10:
            return best_name

    raise ValueError("classifier did not return one configured category or __OTHER__")


def classify_category_rc46(channel: Any, article: Mapping[str, Any] | Any, categories: list[dict[str, Any]]) -> str:
    if not categories:
        return ""

    # RC45's lexical function may have been wrapped by rc45_editorial_fit, which
    # intentionally routes guide/review-like titles to semantic review.
    from . import rc45_policy as rc45

    lexical = rc45.lexical_category(article, categories)
    if lexical:
        LOG.info(
            "RC46 editorial gate article_id=%s category=%s decision=lexical-pass",
            _row_value(article, "id", "?"), lexical,
        )
        return lexical

    names = "\n".join(f"- {item['name']}" for item in categories)
    profile = " ".join(str(getattr(channel, "editorial_profile", "") or "").split())[:1800]
    prompt = f"""You are the channel's assignment editor. Classify ONE source item into ONE operator-defined category.
The source may be English, Ukrainian or Russian. Category labels may be in another language; classify by meaning.
A category is valid only when the item also fits the CHANNEL PROFILE as something this channel should publish.
If the item is outside the profile, an evergreen explainer/listicle/review/conference housekeeping item not requested by the profile, or no category genuinely fits, return __OTHER__.
Do not force an item into the nearest category.
Return only one category name or __OTHER__. JSON like {{"category":"..."}} is accepted.

CHANNEL PROFILE:
{profile or '(not specified)'}

CATEGORIES:
{names}

SOURCE TITLE:
{_row_value(article, 'title')[:800]}

SOURCE EXCERPT:
{_row_value(article, 'raw_text')[:2800]}
"""

    def validator(value: str) -> None:
        extract_category_rc46(value, categories)

    try:
        result = run_ai(
            prompt,
            validator=validator,
            max_output_tokens=64,
            cloud_timeout_seconds=6,
            task_timeout_seconds=12,
            local_repair=False,
            skip_providers={"codex", "local"},
            suppress_provider_on_quota=False,
            allowed_providers={"gemini", "groq", "nvidia", "cloudflare"},
        )
        category = extract_category_rc46(result.text, categories)
        LOG.info(
            "RC46 editorial gate article_id=%s category=%s decision=classified provider=%s",
            _row_value(article, "id", "?"), category, result.provider,
        )
        return category
    except (AIRouterError, ValueError, TypeError) as exc:
        # Infrastructure/format failure is not an editorial judgement. RC45 made
        # this a throughput kill switch. RC46 lets the core factual/newworthiness
        # pipeline continue while recording degraded classification.
        LOG.warning(
            "RC46 editorial gate article_id=%s category=%s decision=classifier-degraded allow=true reason=%s",
            _row_value(article, "id", "?"), _UNCLASSIFIED, str(exc)[:900],
        )
        return _UNCLASSIFIED


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


def _publication_starved(channel: Any, recent: Iterable[Mapping[str, Any] | Any]) -> bool:
    rows = list(recent)
    last = None
    for row in rows:
        last = _parse_dt(_row_value(row, "published_at"))
        if last is not None:
            break
    if last is None:
        return True
    min_gap = max(0, int(getattr(channel, "min_publish_interval_minutes", 0) or 0))
    threshold_minutes = max(45, min_gap * 3)
    age_minutes = (datetime.now(timezone.utc) - last).total_seconds() / 60.0
    return age_minutes >= threshold_minutes


def balance_reject_reason_rc46(
    channel: Any,
    article: Mapping[str, Any] | Any,
    recent: Iterable[Mapping[str, Any] | Any],
    *,
    category: str | None = None,
) -> tuple[str, str]:
    categories = parse_editorial_weights(channel)
    if not categories:
        return "", ""

    rows = list(recent)
    category = str(category or "").strip() or classify_category_rc46(channel, article, categories)
    article_id = _row_value(article, "id", "?")

    if category == _UNCLASSIFIED:
        LOG.warning(
            "RC46 editorial gate article_id=%s category=unclassified decision=degraded-pass reason=classifier-unavailable-or-invalid",
            article_id,
        )
        return "", ""
    if category == _OTHER:
        reason = "EDITORIAL_FIT_RC46_SKIP: матеріал не відповідає редакційному профілю або жодній налаштованій категорії."
        LOG.info("RC46 editorial gate article_id=%s category=%s decision=reject reason=%s", article_id, _OTHER, reason)
        return reason, _OTHER

    weights = {str(item["name"]): float(item["weight"]) for item in categories}
    lookup = {_category_key(name): name for name in weights}
    canonical = lookup.get(_category_key(category))
    if canonical is None:
        LOG.warning(
            "RC46 editorial gate article_id=%s category=%s decision=degraded-pass reason=canonical-mismatch",
            article_id, category,
        )
        return "", ""
    category = canonical
    weight = weights[category]
    positive_total = sum(value for value in weights.values() if value > 0)

    if weight <= 0:
        reason = f"EDITORIAL_WEIGHT_RC46_SKIP: категорія «{category}» має вагу 0 для каналу «{getattr(channel, 'name', '')}»."
        LOG.info("RC46 editorial gate article_id=%s category=%s decision=reject reason=%s", article_id, category, reason)
        return reason, category
    if positive_total <= 0:
        LOG.info("RC46 editorial gate article_id=%s category=%s decision=pass reason=no-positive-weight-total", article_id, category)
        return "", category

    recent_categories: list[str] = []
    for row in rows[:24]:
        value = _row_value(row, "editorial_category").strip()
        current = lookup.get(_category_key(value))
        if current is not None:
            recent_categories.append(current)
    if len(recent_categories) < 5:
        LOG.info("RC46 editorial gate article_id=%s category=%s decision=pass reason=short-history", article_id, category)
        return "", category

    sample = recent_categories[:20]
    count = Counter(sample)[category]
    target = weight / positive_total
    projected = (count + 1) / (len(sample) + 1)
    tolerance = max(0.10, 1.0 / (len(sample) + 1))

    if projected > target + tolerance and count > 0:
        if _publication_starved(channel, rows):
            LOG.info(
                "RC46 editorial gate article_id=%s category=%s decision=starvation-pass current=%s/%s target=%.1f%%",
                article_id, category, count, len(sample), target * 100.0,
            )
            return "", category
        reason = (
            f"EDITORIAL_WEIGHT_RC46_SKIP: «{category}» уже займає {count}/{len(sample)} відомих категорій; "
            f"цільова вага ≈{target * 100.0:.1f}%."
        )
        LOG.info("RC46 editorial gate article_id=%s category=%s decision=reject reason=%s", article_id, category, reason)
        return reason, category

    LOG.info(
        "RC46 editorial gate article_id=%s category=%s decision=pass current=%s/%s target=%.1f%% projected=%.1f%%",
        article_id, category, count, len(sample), target * 100.0, projected * 100.0,
    )
    return "", category


def install_rc46_policy() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from . import rc42_policy as rc42
    from . import rc45_policy as rc45

    # Both language directions ultimately look these globals up at runtime:
    # en→uk through the RC42 wrapper captured by RC45, and uk/ru→en directly
    # through RC45's decide wrapper.
    rc45.classify_category_rc45 = classify_category_rc46
    rc45.balance_reject_reason_rc45 = balance_reject_reason_rc46
    rc42.classify_category = classify_category_rc46
    rc42.balance_reject_reason = balance_reject_reason_rc46
    _INSTALLED = True
