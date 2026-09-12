from __future__ import annotations

import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable

from .. import ai_router as legacy_ai
from ..codex_engine import CodexEngineError, run_codex
from ..local_ai_runtime import LocalAIRuntimeError, generate_local_text
from ..secrets_store import load_secrets
from .domain import AIModelHealth, BlockedBy, ProviderHealth, ProviderState
from .loghub import event
from .storage import V2Store, now_iso


@dataclass(frozen=True, slots=True)
class AIResult:
    text: str
    provider: str
    model: str
    label: str
    attempted: tuple[str, ...] = ()


class GatewayExhausted(RuntimeError):
    def __init__(self, message: str, *, retry_seconds: int = 300, provider_outage: bool = True, failures: Iterable[str] = ()):
        super().__init__(message)
        self.retry_seconds = max(30, int(retry_seconds))
        self.provider_outage = bool(provider_outage)
        self.failures = tuple(failures)


class CandidateRejected(RuntimeError):
    pass


def _cooldown_active(value: str) -> bool:
    if not value:
        return False
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc) > datetime.now(timezone.utc)
    except Exception:
        return False


def _until(seconds: int) -> str:
    if int(seconds) <= 0:
        return ""
    return (datetime.now(timezone.utc) + timedelta(seconds=int(seconds))).astimezone().isoformat(timespec="seconds")


def _failure_meta(exc: Exception) -> tuple[ProviderState, int, str]:
    """Return (state, cooldown_seconds, scope).

    Scope is deliberately conservative:
    - provider: only credentials/configuration that make every model unusable;
    - model: quota/network/timeout/model failures are isolated to one model;
    - task: request size/content-specific failures never poison health.

    This mirrors the working Content Tool router and prevents one dead NVIDIA/Groq
    model from hiding another healthy model behind a provider-wide cooldown.
    """
    kind = str(getattr(exc, "kind", "") or "").casefold()
    text = str(exc).casefold()

    if kind == "auth" or any(x in text for x in ("unauthorized", "forbidden", "invalid api key", "ключ або доступ відхилено")):
        return ProviderState.AUTH_ERROR, 1800, "provider"
    if kind == "configuration" or "не налаштовано" in text:
        return ProviderState.CONFIG_ERROR, 900, "provider"
    if kind == "request_too_large" or any(x in text for x in ("request too large", "context length", "context_length")):
        return ProviderState.MODEL_UNSUPPORTED, 0, "task"
    if kind == "quota" or any(x in text for x in ("quota", "usage limit", "rate limit", "too many requests", "429", "ліміт", "credits exhausted")):
        # Account usage limits are long-lived; ordinary 429/rate limits are shorter.
        # Keep the scope model-level so a sibling model/provider can still work.
        retry_after = int(getattr(exc, "retry_after", 0) or 0)
        if "usage limit" in text or "credits exhausted" in text:
            return ProviderState.QUOTA, min(24 * 3600, max(6 * 3600, retry_after or 0)), "model"
        return ProviderState.QUOTA, min(6 * 3600, max(300, retry_after or 900)), "model"
    if kind in {"gone", "model"} or any(x in text for x in ("model unsupported", "model_not_found", "модель більше недоступна", "end of life", "no longer available")):
        return ProviderState.MODEL_UNSUPPORTED, 6 * 3600, "model"
    if kind == "network" or any(x in text for x in ("network request failed", "connection", "dns", "name resolution")):
        return ProviderState.NETWORK_DOWN, 45, "model"
    if "timeout" in text or "timed out" in text or "не завершила" in text or "перевищено ліміт" in text:
        return ProviderState.TIMEOUT, 90, "model"
    if kind in {"temporary", "bad_response"}:
        return ProviderState.NETWORK_DOWN, 60, "model"
    return ProviderState.NETWORK_DOWN, 60, "model"


class AIGateway:
    """V2 AI router with model-level health and model-level cooldowns.

    Runtime routing uses only the reviewed static allow-list from ``ai_router``.
    Discovery remains a diagnostics concern and never promotes an unreviewed model
    into unattended publication.
    """

    PROVIDER_ORDER = ("codex", "gemini", "nvidia", "groq", "cloudflare", "local")
    # Shared across gateway instances: three channel workers must not hammer the
    # same provider simultaneously when it is slow or rate-limited.
    _PROVIDER_CALL_LOCKS = {name: threading.Lock() for name in PROVIDER_ORDER}

    def __init__(self, store: V2Store):
        self.store = store

    def _provider_call_lock(self, provider: str) -> threading.Lock:
        return self._PROVIDER_CALL_LOCKS.setdefault(str(provider), threading.Lock())

    def _health_map(self) -> dict[str, ProviderHealth]:
        return {item.provider: item for item in self.store.provider_health()}

    def _model_health_map(self) -> dict[tuple[str, str], AIModelHealth]:
        return {(item.provider, item.model): item for item in self.store.ai_model_health()}

    def _configured(self, provider: str, cfg) -> bool:
        if provider == "codex":
            try:
                return bool(legacy_ai._codex_configured_cached())
            except Exception:
                return True
        if provider == "gemini":
            return bool(cfg.gemini_api_key)
        if provider == "nvidia":
            return bool(cfg.nvidia_api_key)
        if provider == "groq":
            return bool(cfg.groq_api_key)
        if provider == "cloudflare":
            return bool(cfg.cloudflare_account_id and cfg.cloudflare_api_token)
        if provider == "local":
            return bool(cfg.local_enabled)
        return False

    def _runtime_slots(self, cfg) -> list[legacy_ai.Slot]:
        # Global reviewed priority is intentional: Codex, Gemini, NVIDIA Ultra,
        # Groq GPT-OSS, NVIDIA Super, Groq Qwen, Cloudflare..., local.
        slots = list(legacy_ai._runtime_model_slots(cfg))
        return sorted(slots, key=lambda item: int(item.priority))

    def _provider_slots(self, provider: str, cfg) -> list[legacy_ai.Slot]:
        return [slot for slot in self._runtime_slots(cfg) if slot.provider == provider]

    def _provider_blocked(self, provider: str) -> bool:
        current = self._health_map().get(provider)
        # Old RC11/12 NETWORK_DOWN/QUOTA rows must NOT suppress the whole provider.
        return bool(
            current
            and current.state in {ProviderState.AUTH_ERROR, ProviderState.CONFIG_ERROR}
            and _cooldown_active(current.cooldown_until)
        )

    def _model_blocked(self, provider: str, model: str) -> bool:
        current = self._model_health_map().get((provider, model))
        return bool(current and _cooldown_active(current.cooldown_until))

    def _mark_model_success(self, provider: str, model: str, detail: str = "") -> None:
        current = self._model_health_map().get((provider, model), AIModelHealth(provider=provider, model=model))
        current.state = ProviderState.HEALTHY
        current.detail = str(detail or "")[:1200]
        current.consecutive_failures = 0
        current.success_count += 1
        current.cooldown_until = ""
        current.updated_at = now_iso()
        self.store.set_ai_model_health(current)

    def _mark_model_failure(self, provider: str, model: str, exc: Exception) -> tuple[ProviderState, str]:
        state, seconds, scope = _failure_meta(exc)
        if scope == "task":
            event("ai", "model task-specific failure", provider=provider, model=model, state=str(state), detail=str(exc)[:600])
            return state, scope

        current = self._model_health_map().get((provider, model), AIModelHealth(provider=provider, model=model))
        current.state = state
        current.detail = str(exc)[:1200]
        current.consecutive_failures += 1
        current.failure_count += 1
        current.cooldown_until = _until(seconds)
        current.updated_at = now_iso()
        self.store.set_ai_model_health(current)

        if scope == "provider":
            provider_health = self._health_map().get(provider, ProviderHealth(provider=provider))
            provider_health.state = state
            provider_health.model = model
            provider_health.detail = str(exc)[:1200]
            provider_health.consecutive_failures += 1
            provider_health.failure_count += 1
            provider_health.cooldown_until = _until(seconds)
            provider_health.updated_at = now_iso()
            self.store.set_provider_health(provider_health)

        event(
            "ai", "model failure", provider=provider, model=model, state=str(state), scope=scope,
            detail=str(exc)[:600], cooldown_seconds=seconds,
        )
        return state, scope

    def _refresh_provider_summary(self, provider: str, cfg) -> ProviderHealth:
        if not self._configured(provider, cfg):
            current = self._health_map().get(provider, ProviderHealth(provider=provider))
            current.state = ProviderState.CONFIG_ERROR
            current.model = ""
            current.detail = "не налаштовано"
            current.cooldown_until = ""
            current.updated_at = now_iso()
            self.store.set_provider_health(current)
            return current

        current = self._health_map().get(provider, ProviderHealth(provider=provider))
        # A real provider-wide credential/configuration failure remains authoritative
        # until its short cooldown expires or a manual/startup probe succeeds.
        if current.state in {ProviderState.AUTH_ERROR, ProviderState.CONFIG_ERROR} and _cooldown_active(current.cooldown_until):
            return current

        models = {slot.model for slot in self._provider_slots(provider, cfg)}
        rows = [item for item in self.store.ai_model_health(provider) if item.model in models]
        healthy_rows = [item for item in rows if item.state == ProviderState.HEALTHY and not _cooldown_active(item.cooldown_until)]
        total = len(models)
        if healthy_rows:
            winner = max(healthy_rows, key=lambda item: item.updated_at or "")
            restored = current.state != ProviderState.HEALTHY
            current.state = ProviderState.HEALTHY
            current.model = winner.model
            current.detail = f"моделей healthy {len(healthy_rows)}/{total}; активна {winner.model}"
            current.consecutive_failures = 0
            current.success_count = sum(item.success_count for item in rows)
            current.failure_count = sum(item.failure_count for item in rows)
            current.cooldown_until = ""
            current.updated_at = now_iso()
            self.store.set_provider_health(current)
            if restored:
                woke = self.store.wake_blocked(BlockedBy.AI, limit=500)
                event("ai", "provider restored", provider=provider, model=winner.model, healthy_models=len(healthy_rows), total_models=total, woke_waiting_ai=woke)
            return current

        if rows:
            latest = max(rows, key=lambda item: item.updated_at or "")
            current.state = latest.state
            current.model = latest.model
            current.detail = f"0/{total} моделей healthy; остання: {latest.model}: {latest.detail[:700]}"
            current.consecutive_failures = sum(item.consecutive_failures for item in rows)
            current.success_count = sum(item.success_count for item in rows)
            current.failure_count = sum(item.failure_count for item in rows)
            # This is an aggregate display field, NOT a provider-wide runtime block.
            current.cooldown_until = ""
            current.updated_at = now_iso()
            self.store.set_provider_health(current)
            return current

        current.state = ProviderState.UNKNOWN
        current.model = ""
        current.detail = f"0/{total} моделей перевірено"
        current.cooldown_until = ""
        current.updated_at = now_iso()
        self.store.set_provider_health(current)
        return current

    def _mark_success(self, provider: str, slot_model: str, runtime_model: str, detail: str = "") -> None:
        self._mark_model_success(provider, slot_model, detail or f"success via {runtime_model}")
        # Successful request proves provider accessibility even if an old AUTH/CONFIG
        # cooldown existed; clear that stale provider-wide block immediately.
        current = self._health_map().get(provider, ProviderHealth(provider=provider))
        restored = current.state != ProviderState.HEALTHY
        current.state = ProviderState.HEALTHY
        current.model = runtime_model or slot_model
        current.detail = detail or "AI request OK"
        current.consecutive_failures = 0
        current.cooldown_until = ""
        current.updated_at = now_iso()
        self.store.set_provider_health(current)
        if restored:
            woke = self.store.wake_blocked(BlockedBy.AI, limit=500)
            event("ai", "provider restored", provider=provider, model=current.model, woke_waiting_ai=woke)

    def _call_slot(self, slot: legacy_ai.Slot, cfg, prompt: str, *, max_output_tokens: int, timeout_seconds: int) -> tuple[str, str, str]:
        if slot.provider == "codex":
            try:
                return str(run_codex(prompt)).strip(), slot.model, slot.label
            except CodexEngineError as exc:
                low = str(exc).casefold()
                kind = "quota" if any(x in low for x in ("usage limit", "quota", "rate limit", "429", "credits")) else "temporary"
                raise legacy_ai.AIModelError(str(exc), kind=kind) from exc
        if slot.provider == "gemini":
            return str(legacy_ai._gemini(slot, cfg, prompt, max_output_tokens=max_output_tokens, timeout_seconds=timeout_seconds)).strip(), slot.model, slot.label
        if slot.provider in {"nvidia", "groq", "cloudflare"}:
            return str(legacy_ai._openai(slot, cfg, prompt, max_output_tokens=max_output_tokens, timeout_seconds=timeout_seconds)).strip(), slot.model, slot.label
        if slot.provider == "local":
            try:
                text, target = generate_local_text(
                    preferred_model=cfg.local_model, manual_base_url=cfg.local_base_url, manual_model=cfg.local_model,
                    prompt=prompt, max_output_tokens=max_output_tokens, temperature=0.0, timeout_seconds=max(8, timeout_seconds),
                )
                return str(text).strip(), str(getattr(target, "model", "") or slot.model), str(getattr(target, "label", "") or slot.label)
            except LocalAIRuntimeError as exc:
                raise legacy_ai.AIModelError(str(exc), kind="temporary") from exc
        raise legacy_ai.AIModelError(f"Unknown provider {slot.provider}", kind="configuration")

    def run(
        self, prompt: str, *, validator: Callable[[str], object] | None = None, max_output_tokens: int = 800,
        timeout_seconds: int = 25, allowed_providers: Iterable[str] | None = None,
    ) -> AIResult:
        text_prompt = str(prompt or "").strip()
        if not text_prompt:
            raise ValueError("Empty AI prompt")
        cfg = load_secrets()
        allowed = None if allowed_providers is None else {str(x).casefold() for x in allowed_providers}
        attempted: list[str] = []
        failures: list[str] = []
        validation_failures = 0
        configured_providers: set[str] = set()
        provider_suppressed: set[str] = set()

        for slot in self._runtime_slots(cfg):
            provider = slot.provider
            if allowed is not None and provider not in allowed:
                continue
            if not self._configured(provider, cfg):
                continue
            configured_providers.add(provider)
            if provider in provider_suppressed or self._provider_blocked(provider):
                continue
            if self._model_blocked(provider, slot.model):
                continue

            attempted.append(f"{provider}:{slot.model}")
            started = time.monotonic()
            lock = self._provider_call_lock(provider)
            acquired = lock.acquire(timeout=min(2.0, max(0.25, float(timeout_seconds) * 0.08)))
            if not acquired:
                failures.append(f"{slot.label}: provider busy")
                event("ai", "provider busy; trying next route", provider=provider, model=slot.model)
                continue
            try:
                try:
                    output, runtime_model, label = self._call_slot(
                        slot, cfg, text_prompt, max_output_tokens=max_output_tokens, timeout_seconds=timeout_seconds,
                    )
                finally:
                    lock.release()
                if not output:
                    raise legacy_ai.AIModelError("Провайдер повернув порожню відповідь", kind="bad_response")
                if validator is not None:
                    try:
                        validator(output)
                    except Exception as exc:
                        validation_failures += 1
                        failures.append(f"{label}: QA: {exc}")
                        event("ai", "candidate rejected by QA", provider=provider, model=runtime_model, elapsed=round(time.monotonic() - started, 2), detail=str(exc)[:500])
                        continue
                self._mark_success(provider, slot.model, runtime_model)
                summary = self._refresh_provider_summary(provider, cfg)
                event(
                    "ai", "AI success", provider=provider, model=runtime_model, elapsed=round(time.monotonic() - started, 2),
                    chars=len(output), provider_state=str(summary.state), attempted=len(attempted),
                )
                return AIResult(output, provider, runtime_model, label, tuple(attempted))
            except Exception as exc:
                failures.append(f"{slot.label}: {exc}")
                state, scope = self._mark_model_failure(provider, slot.model, exc)
                if scope == "provider":
                    provider_suppressed.add(provider)
                # Every model-level failure falls through to the next reviewed slot.
                # Because global priorities are interleaved, Groq can be tried before
                # NVIDIA's secondary model, and NVIDIA Super still remains reachable.
                continue

        if configured_providers:
            for provider in configured_providers:
                self._refresh_provider_summary(provider, cfg)
        else:
            raise GatewayExhausted("Не налаштовано жодного AI-провайдера.", retry_seconds=600, provider_outage=True, failures=failures)

        if validation_failures and validation_failures >= len(attempted) and attempted:
            raise GatewayExhausted(
                "AI відповів, але всі кандидати відхилені редакційним QA. " + " | ".join(failures[-6:]),
                retry_seconds=180, provider_outage=False, failures=failures,
            )
        raise GatewayExhausted(
            "Тимчасово немає придатного AI-маршруту. " + " | ".join(failures[-6:]),
            retry_seconds=180, provider_outage=True, failures=failures,
        )

    def _probe_provider(self, provider: str, cfg) -> ProviderHealth:
        if not self._configured(provider, cfg):
            return self._refresh_provider_summary(provider, cfg)

        success = False
        provider_scope_failure = False
        for slot in self._provider_slots(provider, cfg):
            started = time.monotonic()
            lock = self._provider_call_lock(provider)
            acquired = lock.acquire(timeout=2.0)
            if not acquired:
                event("ai", "health probe provider busy", provider=provider, model=slot.model)
                continue
            try:
                try:
                    # 32 tokens is too small for some reasoning models which can
                    # consume the entire budget before emitting visible text.
                    text, runtime_model, _label = self._call_slot(
                        slot, cfg, "Reply with OK only.", max_output_tokens=128, timeout_seconds=18
                    )
                finally:
                    lock.release()
                if not text:
                    raise legacy_ai.AIModelError("empty health response", kind="bad_response")
                self._mark_success(provider, slot.model, runtime_model, "health probe OK")
                event("ai", "model health probe success", provider=provider, model=runtime_model, elapsed=round(time.monotonic() - started, 2))
                success = True
                break
            except Exception as exc:
                _state, scope = self._mark_model_failure(provider, slot.model, exc)
                event("ai", "model health probe failed", provider=provider, model=slot.model, scope=scope, elapsed=round(time.monotonic() - started, 2), detail=str(exc)[:500])
                if scope == "provider":
                    provider_scope_failure = True
                    break
                continue

        summary = self._refresh_provider_summary(provider, cfg)
        if success and summary.state != ProviderState.HEALTHY:
            summary.state = ProviderState.HEALTHY
            summary.cooldown_until = ""
            summary.updated_at = now_iso()
            self.store.set_provider_health(summary)
        elif provider_scope_failure:
            summary = self._health_map().get(provider, summary)
        return summary

    def probe_all(self) -> list[ProviderHealth]:
        """Live-probe configured providers concurrently, models sequentially per provider.

        One failed sibling model no longer marks its provider dead. Provider probes run
        in parallel so startup/manual health checking is bounded by the slowest provider
        rather than the sum of six provider timeouts.
        """
        cfg = load_secrets()
        by_provider: dict[str, ProviderHealth] = {}
        with ThreadPoolExecutor(max_workers=len(self.PROVIDER_ORDER), thread_name_prefix="ai-probe") as pool:
            futures = {pool.submit(self._probe_provider, provider, cfg): provider for provider in self.PROVIDER_ORDER}
            for future in as_completed(futures):
                provider = futures[future]
                try:
                    by_provider[provider] = future.result()
                except Exception as exc:
                    event("ai", "provider health probe crashed", provider=provider, detail=str(exc)[:700])
                    current = self._health_map().get(provider, ProviderHealth(provider=provider))
                    current.state = ProviderState.NETWORK_DOWN
                    current.detail = str(exc)[:1200]
                    current.updated_at = now_iso()
                    self.store.set_provider_health(current)
                    by_provider[provider] = current
        return [by_provider.get(provider) or self._refresh_provider_summary(provider, cfg) for provider in self.PROVIDER_ORDER]
