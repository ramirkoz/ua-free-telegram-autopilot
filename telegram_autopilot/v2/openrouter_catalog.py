from __future__ import annotations

import json
import math
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from ..network import fetch_url
from ..paths import cache_dir


@dataclass(frozen=True, slots=True)
class OpenRouterModel:
    id: str
    name: str
    prompt_price: float
    completion_price: float
    context_length: int
    quality: int
    free: bool

    @property
    def blended_price_million(self) -> float:
        return (self.prompt_price * 0.82 + self.completion_price * 0.18) * 1_000_000


_LOCK = threading.RLock()
_CATALOG: tuple[OpenRouterModel, ...] = ()
_CATALOG_AT = 0.0
_TTL = 6 * 60 * 60
_SKIP = ("image", "embedding", "rerank", "audio", "speech", "tts", "transcription", "video")
_UNSUPPORTED_ROUTE_SUFFIXES = (":batch",)  # Batch-only adapters cannot serve chat/completions.


def _chat_compatible_id(model_id: str) -> bool:
    return bool(model_id) and not model_id.casefold().endswith(_UNSUPPORTED_ROUTE_SUFFIXES)



def _cache_path() -> Path:
    return cache_dir() / "openrouter_models_cache.json"


def _price(value: object) -> float:
    try:
        result = float(str(value or "0"))
    except Exception:
        return math.inf
    return result if result >= 0 else math.inf


def _quality_hint(model_id: str, name: str) -> int:
    text = f"{model_id} {name}".casefold()
    quality = 1
    if any(token in text for token in (
        "claude-sonnet", "claude-opus", "gpt-5", "gpt-6", "gemini-3",
        "gemini-2.5-pro", "grok-4",
    )):
        quality = 4
    elif any(token in text for token in (
        "120b", "235b", "400b", "550b", "671b", "large", "max", "pro", "ultra",
        "gpt-oss-120", "deepseek", "qwen3", "qwen-3", "glm-5", "glm5", "kimi-k2", "nemotron",
    )):
        quality = 3
    elif any(token in text for token in ("medium", "mistral", "command-r", "70b", "72b")):
        quality = 2
    if any(token in text for token in ("nano", "tiny", "micro")):
        return 1
    if any(token in text for token in ("mini", "small", "lite", "flash")):
        quality = min(quality, 2)
    return quality


def _parse(payload: object) -> tuple[OpenRouterModel, ...]:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise RuntimeError("OpenRouter повернув неправильний каталог моделей.")
    rows: list[OpenRouterModel] = []
    for raw in payload["data"]:
        if not isinstance(raw, dict):
            continue
        model_id = str(raw.get("id") or "").strip()
        name = str(raw.get("name") or model_id).strip()
        if not _chat_compatible_id(model_id) or any(part in model_id.casefold() for part in _SKIP):
            continue
        architecture = raw.get("architecture") if isinstance(raw.get("architecture"), dict) else {}
        outputs = architecture.get("output_modalities") if isinstance(architecture, dict) else None
        if isinstance(outputs, list) and "text" not in {str(x).casefold() for x in outputs}:
            continue
        pricing = raw.get("pricing") if isinstance(raw.get("pricing"), dict) else {}
        prompt = _price(pricing.get("prompt"))
        completion = _price(pricing.get("completion"))
        if not math.isfinite(prompt) or not math.isfinite(completion):
            continue
        context = int(raw.get("context_length") or 0)
        if context and context < 12_000:
            continue
        rows.append(OpenRouterModel(
            id=model_id,
            name=name,
            prompt_price=prompt,
            completion_price=completion,
            context_length=context,
            quality=_quality_hint(model_id, name),
            free=prompt == 0.0 and completion == 0.0,
        ))
    if not rows:
        raise RuntimeError("OpenRouter не повернув придатних текстових моделей.")
    return tuple(rows)


def _load_cache() -> tuple[OpenRouterModel, ...]:
    try:
        raw = json.loads(_cache_path().read_text(encoding="utf-8"))
        rows = raw.get("models") if isinstance(raw, dict) else None
        if not isinstance(rows, list):
            return ()
        return tuple(OpenRouterModel(
            id=str(row["id"]),
            name=str(row.get("name") or row["id"]),
            prompt_price=float(row.get("prompt_price") or 0.0),
            completion_price=float(row.get("completion_price") or 0.0),
            context_length=int(row.get("context_length") or 0),
            quality=_quality_hint(str(row["id"]), str(row.get("name") or row["id"])),
            free=bool(row.get("free", False)),
        ) for row in rows if isinstance(row, dict) and _chat_compatible_id(str(row.get("id") or "")))
    except Exception:
        return ()


def _save_cache(rows: tuple[OpenRouterModel, ...]) -> None:
    payload = {"models": [
        {
            "id": row.id,
            "name": row.name,
            "prompt_price": row.prompt_price,
            "completion_price": row.completion_price,
            "context_length": row.context_length,
            "free": row.free,
        }
        for row in rows
    ]}
    path = _cache_path()
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)


def model_catalog(*, force: bool = False, timeout: float = 20.0) -> tuple[OpenRouterModel, ...]:
    global _CATALOG, _CATALOG_AT
    now = time.time()
    with _LOCK:
        if _CATALOG and not force and now - _CATALOG_AT < _TTL:
            return _CATALOG
    try:
        response = fetch_url(
            "https://openrouter.ai/api/v1/models",
            headers={"Accept": "application/json"},
            timeout=timeout,
            max_bytes=12 * 1024 * 1024,
            allowed_content_types={"application/json"},
            max_redirects=0,
            allow_http_errors=True,
        )
        if response.status >= 400:
            raise RuntimeError(f"OpenRouter catalog HTTP {response.status}")
        parsed = _parse(response.json())
        with _LOCK:
            _CATALOG, _CATALOG_AT = parsed, now
        try:
            _save_cache(parsed)
        except OSError:
            pass
        return parsed
    except Exception:
        cached = _load_cache()
        if cached:
            with _LOCK:
                _CATALOG, _CATALOG_AT = cached, now
            return cached
        raise


def recommended_models(*, strategy: str = "balanced", limit: int = 6, force: bool = False) -> tuple[OpenRouterModel, ...]:
    rows = [row for row in model_catalog(force=force) if _chat_compatible_id(row.id)]
    strategy = str(strategy or "balanced").strip().casefold()
    if strategy not in {"economy", "balanced", "quality"}:
        strategy = "balanced"
    min_quality = {"economy": 1, "balanced": 2, "quality": 3}[strategy]
    cap = {"economy": 3.0, "balanced": 18.0, "quality": 80.0}[strategy]
    eligible = [row for row in rows if row.quality >= min_quality and row.blended_price_million <= cap]
    if strategy != "economy":
        paid = [row for row in eligible if not row.free]
        if paid:
            eligible = paid
    if strategy == "quality":
        eligible.sort(key=lambda row: (-row.quality, row.blended_price_million, -row.context_length, row.id))
    else:
        eligible.sort(key=lambda row: (row.blended_price_million, -row.quality, -row.context_length, row.id))
    selected: list[OpenRouterModel] = []
    families: set[str] = set()
    for row in eligible:
        family = row.id.casefold().split(":", 1)[0].split("/", 1)[-1].split("-", 1)[0]
        if family in families and len(selected) < 3:
            continue
        selected.append(row)
        families.add(family)
        if len(selected) >= max(1, min(12, int(limit))):
            break
    return tuple(selected)


def recommended_model_ids(*, strategy: str = "balanced", limit: int = 6, force: bool = False) -> tuple[str, ...]:
    return tuple(row.id for row in recommended_models(strategy=strategy, limit=limit, force=force))

_TIER_RANK = {
    "fast_cheap": 1,
    "balanced": 2,
    "strong": 3,
    "premium": 4,
}


def route_tiers(purpose: str, strategy: str) -> tuple[str, str]:
    value = str(purpose or "content").strip().casefold()
    strategy = str(strategy or "balanced").strip().casefold()
    if value in {"editorial_selector", "monitoring_selector", "value_gate", "health_probe"}:
        start, ceiling = "fast_cheap", "strong"
    elif value in {"fact", "quality", "research", "deep_review"}:
        start, ceiling = "strong", "premium"
    elif value in {"writer", "final_editor", "complex_rewrite", "rewrite"}:
        start, ceiling = "strong", "premium"
    else:
        start, ceiling = "balanced", "strong"

    if strategy == "economy":
        if start == "strong" and value not in {"fact", "quality", "research", "deep_review"}:
            start = "balanced"
        ceiling = "strong"
    elif strategy == "quality":
        if start == "fast_cheap":
            start = "balanced"
        elif start == "balanced":
            start = "strong"
        ceiling = "premium"
    return start, ceiling


def candidate_models_for_task(
    *,
    purpose: str,
    prompt_chars: int,
    max_output_tokens: int,
    strategy: str = "balanced",
    limit: int = 5,
    force: bool = False,
) -> tuple[OpenRouterModel, ...]:
    editorial_task = str(purpose or "").strip().casefold() in {"writer", "final_editor", "complex_rewrite", "rewrite"}
    # Agentic research ensembles are expensive and are not default copywriters.
    # Explicit operator-configured model IDs use a separate route.
    catalog = tuple(
        row for row in model_catalog(force=force)
        if _chat_compatible_id(row.id)
        and (not editorial_task or "multi-agent" not in row.id.casefold())
    )
    start, ceiling = route_tiers(purpose, strategy)
    start_rank = _TIER_RANK[start]
    ceiling_rank = _TIER_RANK[ceiling]
    estimated_prompt_tokens = max(64, int(max(0, prompt_chars) / 3.5))
    required_context = max(12_000, estimated_prompt_tokens + max(1, int(max_output_tokens)) * 2 + 2_000)
    cap_by_tier = {1: 1.5, 2: 5.0, 3: 18.0, 4: 80.0}
    strategy = str(strategy or "balanced").strip().casefold()
    selected: list[OpenRouterModel] = []
    seen: set[str] = set()

    for tier_rank in range(start_rank, ceiling_rank + 1):
        cap = cap_by_tier[tier_rank]
        if strategy == "economy":
            cap *= 0.65
        elif strategy == "quality":
            cap *= 1.7

        eligible = [
            row for row in catalog
            if row.quality >= tier_rank
            and (not row.context_length or row.context_length >= required_context)
            and row.blended_price_million <= cap
            and (strategy == "economy" or not row.free)
        ]
        if not eligible and strategy != "economy":
            eligible = [
                row for row in catalog
                if row.quality >= tier_rank
                and (not row.context_length or row.context_length >= required_context)
                and row.blended_price_million <= cap
            ]
        # Editorial generation must prefer proven quality, not the cheapest viable model.
        # Preserve budget caps and task-tier eligibility.
        if str(purpose or "").strip().casefold() in {"writer", "final_editor", "complex_rewrite", "rewrite"}:
            eligible.sort(key=lambda row: (-row.quality, -row.context_length, row.blended_price_million, row.id))
        else:
            eligible.sort(key=lambda row: (row.blended_price_million, -row.quality, -row.context_length, row.id))
        for row in eligible[:8]:
            if row.id in seen:
                continue
            selected.append(row)
            seen.add(row.id)
            if len(selected) >= max(1, min(8, int(limit))):
                return tuple(selected)
    return tuple(selected)


def candidate_model_ids_for_task(
    *,
    purpose: str,
    prompt_chars: int,
    max_output_tokens: int,
    strategy: str = "balanced",
    limit: int = 5,
    force: bool = False,
) -> tuple[str, ...]:
    return tuple(
        row.id
        for row in candidate_models_for_task(
            purpose=purpose,
            prompt_chars=prompt_chars,
            max_output_tokens=max_output_tokens,
            strategy=strategy,
            limit=limit,
            force=force,
        )
    )

