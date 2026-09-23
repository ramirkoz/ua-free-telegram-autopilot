from __future__ import annotations

import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable

from .. import ai_router as legacy_ai
from ..codex_engine import CodexEngineError, inspect_codex, run_codex
from ..local_ai_runtime import LocalAIRuntimeError, generate_local_text
from ..secrets_store import load_secrets
from .domain import AIModelHealth, BlockedBy, ProviderHealth, ProviderState
from .loghub import event
from .provider_api import ProviderAPIError, gemini_generate, openai_compatible_chat
from .storage import V2Store, now_iso


@dataclass(frozen=True, slots=True)
class AIResult:
    text: str
    provider: str
    model: str
    label: str
    attempted: tuple[str, ...] = ()


class GatewayExhausted(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        retry_seconds: int = 300,
        provider_outage: bool = True,
        failures: Iterable[str] = (),
    ) -> None:
        super().__init__(message)
        self.retry_seconds = max(30, int(retry_seconds))
        self.provider_outage = bool(provider_outage)
        self.failures = tuple(failures)


class CandidateRejected(RuntimeError):
    pass


# V2 owns the reviewed production routing list. Provider discovery may be used for
# diagnostics, but a newly exposed remote model never becomes an unattended writer
# until it is explicitly reviewed here.
PRODUCTION_SLOTS: tuple[legacy_ai.Slot, ...] = (
    legacy_ai.Slot(1, "gemini", "gemini-3.5-flash", "Gemini 3.5 Flash / Google", "gemini"),
    legacy_ai.Slot(2, "nvidia", "nvidia/nemotron-3-ultra-550b-a55b", "Nemotron 3 Ultra 550B / NVIDIA"),
    legacy_ai.Slot(3, "groq", "openai/gpt-oss-120b", "GPT-OSS 120B / Groq"),
    legacy_ai.Slot(4, "nvidia", "nvidia/nemotron-3-super-120b-a12b", "Nemotron 3 Super 120B / NVIDIA"),
    legacy_ai.Slot(5, "groq", "qwen/qwen3.8-27b", "Qwen 3.8 27B / Groq"),
    legacy_ai.Slot(6, "cloudflare", "@cf/nvidia/nemotron-3-120b-a12b", "Nemotron 3 120B / Cloudflare"),
    legacy_ai.Slot(7, "cloudflare", "@cf/zai-org/glm-4.7-flash", "GLM-4.7 Flash / Cloudflare"),
    legacy_ai.Slot(8, "local", "local-model", "Локальний AI · авто: Ollama → llama.cpp", "local"),
    legacy_ai.Slot(9, "codex", "codex-chatgpt", "Codex / ChatGPT", "codex"),
)


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


def _codex_retry_after_seconds(message: str) -> int:
    text = str(message or "")
    match = re.search(
        r"(?:try\s+again\s+at|reset(?:s)?\s+at)\s+"
        r"([A-Za-z]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?,\s*(\d{4})\s+"
        r"(\d{1,2}):(\d{2})\s*(AM|PM)",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return 0
    month, day, year, hour, minute, ampm = match.groups()
    raw = f"{month} {day} {year} {hour}:{minute} {ampm.upper()}"
    parsed = None
    for fmt in ("%b %d %Y %I:%M %p", "%B %d %Y %I:%M %p"):
        try:
            parsed = datetime.strptime(raw, fmt)
            break
        except ValueError:
            continue
    if parsed is None:
        return 0
    local_tz = datetime.now().astimezone().tzinfo or timezone.utc
    parsed = parsed.replace(tzinfo=local_tz)
    delta = int((parsed.astimezone(timezone.utc) - datetime.now(timezone.utc)).total_seconds()) + 90
    return min(14 * 24 * 3600, max(0, delta))


def _compact_local_prompt(prompt: str, *, limit: int) -> str:
    text = str(prompt or "").strip()
    if len(text) <= limit:
        return text
    marker = "\n\n[... локальний CPU-контекст скорочено без зміни вимог до відповіді ...]\n\n"
    # Keep policy/instructions from the front and output/evidence tail. This is much
    # cheaper than feeding a 4B CPU model the full cloud prompt for every attempt.
    head = max(1200, int(limit * 0.57))
    tail = max(900, limit - head - len(marker))
    return text[:head].rstrip() + marker + text[-tail:].lstrip()


def _failure_meta(exc: Exception) -> tuple[ProviderState, int, str]:
    """Return (visible state, cooldown seconds, scope).

    Only genuine transport/auth/quota/model failures poison model health. A valid
    HTTP/local response that fails article QA is a task failure and MUST NOT become
    NETWORK_DOWN. That distinction is the core RC46 health fix.
    """
    kind = str(getattr(exc, "kind", "") or "").casefold()
    text = str(exc).casefold()
    retry_after = int(getattr(exc, "retry_after", 0) or 0)

    if kind == "auth" or any(x in text for x in ("unauthorized", "forbidden", "invalid api key", "credentials/access rejected")):
        return ProviderState.AUTH_ERROR, 1800, "provider"
    if kind == "configuration" or "не налаштовано" in text or "is missing" in text:
        return ProviderState.CONFIG_ERROR, 900, "provider"
    if kind == "quota" or any(x in text for x in ("usage limit", "quota/rate limit", "credits exhausted")):
        if "usage limit" in text or "credits exhausted" in text:
            return ProviderState.QUOTA, min(14 * 24 * 3600, max(6 * 3600, retry_after or 24 * 3600)), "model"
        return ProviderState.QUOTA, min(6 * 3600, max(300, retry_after or 900)), "model"
    if kind in {"gone", "model"} or any(x in text for x in ("model_not_found", "model unavailable", "unknown model", "end of life")):
        return ProviderState.MODEL_UNSUPPORTED, 6 * 3600, "model"
    if kind == "request_too_large" or any(x in text for x in ("request too large", "context length", "context_length")):
        return ProviderState.MODEL_UNSUPPORTED, 0, "task"
    if kind == "timeout" or any(x in text for x in ("timed out", "не завершила", "перевищено ліміт")):
        return ProviderState.TIMEOUT, 120, "model"
    if kind == "network" or any(x in text for x in ("network request failed", "dns", "name resolution")):
        return ProviderState.NETWORK_DOWN, 60, "model"
    if kind in {"bad_response", "validation", "quality"}:
        return ProviderState.UNKNOWN, 0, "task"
    if kind == "temporary":
        return ProviderState.NETWORK_DOWN, 60, "model"
    return ProviderState.UNKNOWN, 0, "task"


class AIGateway:
    """Modular V2 AI router with provider-aware health and local full fallback."""

    # Codex uses the user's ChatGPT plan quota, so it is a trusted reserve, not
    # the default engine for every selector/value task. Cheap direct providers run
    # first; Codex remains available as the final cloud fallback.
    PROVIDER_ORDER = ("gemini", "nvidia", "groq", "cloudflare", "local", "codex")
    LOCAL_SHORT_TASK_MAX_OUTPUT = 220
    LOCAL_LONG_MAX_OUTPUT = 720
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
            if not bool(getattr(cfg, "codex_enabled", False)):
                return False
            # A transient account inspection failure is not the same thing as an
            # absent configuration. The actual probe/call decides auth/quota/network.
            try:
                status = inspect_codex()
                return bool(status.installed)
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
        del cfg
        return list(PRODUCTION_SLOTS)

    def _provider_slots(self, provider: str, cfg) -> list[legacy_ai.Slot]:
        return [slot for slot in self._runtime_slots(cfg) if slot.provider == provider]

    def _provider_blocked(self, provider: str) -> bool:
        current = self._health_map().get(provider)
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
        current.detail = str(detail or "request OK")[:1200]
        current.consecutive_failures = 0
        current.success_count += 1
        current.cooldown_until = ""
        current.updated_at = now_iso()
        self.store.set_ai_model_health(current)

    def _mark_task_failure(self, provider: str, model: str, exc: Exception) -> None:
        event(
            "ai",
            "AI output/task failure; provider health preserved",
            provider=provider,
            model=model,
            detail=str(exc)[:700],
        )

    def _mark_model_failure(self, provider: str, model: str, exc: Exception) -> tuple[ProviderState, str]:
        state, seconds, scope = _failure_meta(exc)
        if scope == "task":
            self._mark_task_failure(provider, model, exc)
            return state, scope

        current = self._model_health_map().get((provider, model), AIModelHealth(provider=provider, model=model))
        next_failure = int(current.consecutive_failures or 0) + 1
        if provider == "local" and state == ProviderState.TIMEOUT:
            # Local CPU can recover immediately after a single slow article. Do not
            # repeat RC42's 30-minute self-ban.
            seconds = min(max(seconds, 120), 300)
        elif state == ProviderState.NETWORK_DOWN and next_failure >= 2:
            seconds = max(seconds, min(600, 60 * (2 ** min(3, next_failure - 1))))
        current.state = state
        current.detail = str(exc)[:1200]
        current.consecutive_failures = next_failure
        current.failure_count += 1
        current.cooldown_until = _until(seconds)
        current.updated_at = now_iso()
        self.store.set_ai_model_health(current)

        if scope == "provider":
            health = self._health_map().get(provider, ProviderHealth(provider=provider))
            health.state = state
            health.model = model
            health.detail = str(exc)[:1200]
            health.consecutive_failures += 1
            health.failure_count += 1
            health.cooldown_until = _until(seconds)
            health.updated_at = now_iso()
            self.store.set_provider_health(health)

        event(
            "ai",
            "model failure",
            provider=provider,
            model=model,
            state=str(state),
            scope=scope,
            cooldown_seconds=seconds,
            detail=str(exc)[:700],
        )
        return state, scope

    def _refresh_provider_summary(self, provider: str, cfg) -> ProviderHealth:
        current = self._health_map().get(provider, ProviderHealth(provider=provider))
        if provider == "codex" and not bool(getattr(cfg, "codex_enabled", False)):
            current.state = ProviderState.UNKNOWN
            current.model = ""
            current.detail = "вимкнено вручну"
            current.cooldown_until = ""
            current.updated_at = now_iso()
            self.store.set_provider_health(current)
            return current
        if not self._configured(provider, cfg):
            current.state = ProviderState.CONFIG_ERROR
            current.model = ""
            current.detail = "не налаштовано / secret відсутній"
            current.cooldown_until = ""
            current.updated_at = now_iso()
            self.store.set_provider_health(current)
            return current

        models = {slot.model for slot in self._provider_slots(provider, cfg)}
        rows = [item for item in self.store.ai_model_health(provider) if item.model in models]
        healthy = [item for item in rows if item.state == ProviderState.HEALTHY and not _cooldown_active(item.cooldown_until)]
        total = len(models)
        if healthy:
            winner = max(healthy, key=lambda item: item.updated_at or "")
            restored = current.state != ProviderState.HEALTHY
            current.state = ProviderState.HEALTHY
            current.model = winner.model
            current.detail = f"моделей healthy {len(healthy)}/{total}; активна {winner.model}"
            current.consecutive_failures = 0
            current.success_count = sum(int(item.success_count or 0) for item in rows)
            current.failure_count = sum(int(item.failure_count or 0) for item in rows)
            current.cooldown_until = ""
            current.updated_at = now_iso()
            self.store.set_provider_health(current)
            if restored:
                woke = self.store.wake_blocked(BlockedBy.AI, limit=500)
                event("ai", "provider restored", provider=provider, model=winner.model, woke_waiting_ai=woke)
            return current

        if rows:
            latest = max(rows, key=lambda item: item.updated_at or "")
            current.state = latest.state
            current.model = latest.model
            current.detail = f"0/{total} моделей healthy; остання: {latest.model}: {latest.detail[:700]}"
            current.consecutive_failures = sum(int(item.consecutive_failures or 0) for item in rows)
            current.success_count = sum(int(item.success_count or 0) for item in rows)
            current.failure_count = sum(int(item.failure_count or 0) for item in rows)
            active = [item.cooldown_until for item in rows if _cooldown_active(item.cooldown_until)]
            current.cooldown_until = min(active) if active else ""
        else:
            current.state = ProviderState.UNKNOWN
            current.model = ""
            current.detail = f"0/{total} моделей перевірено"
            current.cooldown_until = ""
        current.updated_at = now_iso()
        self.store.set_provider_health(current)
        return current

    def _mark_success(self, provider: str, slot_model: str, runtime_model: str, detail: str = "") -> None:
        self._mark_model_success(provider, slot_model, detail or f"success via {runtime_model}")
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

    def _call_slot(
        self,
        slot: legacy_ai.Slot,
        cfg,
        prompt: str,
        *,
        max_output_tokens: int,
        timeout_seconds: int,
        json_mode: bool = False,
    ) -> tuple[str, str, str]:
        provider = slot.provider
        if provider == "codex":
            try:
                return str(run_codex(prompt)).strip(), slot.model, slot.label
            except CodexEngineError as exc:
                low = str(exc).casefold()
                if any(x in low for x in ("usage limit", "quota", "rate limit", "429", "credits")):
                    retry = _codex_retry_after_seconds(str(exc))
                    raise ProviderAPIError(str(exc), kind="quota", retry_after=retry or None) from exc
                if any(x in low for x in ("login", "auth", "not authenticated", "не авториз")):
                    raise ProviderAPIError(str(exc), kind="auth") from exc
                raise ProviderAPIError(str(exc), kind="temporary") from exc

        if provider == "gemini":
            reply = gemini_generate(
                model=slot.model,
                api_key=cfg.gemini_api_key,
                prompt=prompt,
                max_output_tokens=max_output_tokens,
                timeout_seconds=max(8, int(timeout_seconds)),
                json_mode=json_mode,
            )
            return reply.text, reply.model, slot.label

        if provider in {"nvidia", "groq", "cloudflare"}:
            key = {
                "nvidia": cfg.nvidia_api_key,
                "groq": cfg.groq_api_key,
                "cloudflare": cfg.cloudflare_api_token,
            }[provider]
            reply = openai_compatible_chat(
                provider,
                model=slot.model,
                api_key=key,
                account_id=getattr(cfg, "cloudflare_account_id", ""),
                prompt=prompt,
                max_output_tokens=max_output_tokens,
                timeout_seconds=max(8, int(timeout_seconds)),
                json_mode=json_mode,
            )
            return reply.text, reply.model, slot.label

        if provider == "local":
            requested = int(max_output_tokens)
            short = requested <= self.LOCAL_SHORT_TASK_MAX_OUTPUT
            local_prompt = _compact_local_prompt(prompt, limit=3200 if short else 5600)
            local_budget = max(48, min(requested, self.LOCAL_SHORT_TASK_MAX_OUTPUT if short else self.LOCAL_LONG_MAX_OUTPUT))
            if local_budget <= 96 and len(local_prompt) <= 1600:
                local_timeout = 90
            elif short:
                local_timeout = 120
            else:
                local_timeout = 300
            try:
                text, target = generate_local_text(
                    preferred_model=cfg.local_model,
                    manual_base_url=cfg.local_base_url,
                    manual_model=cfg.local_model,
                    prompt=local_prompt,
                    max_output_tokens=local_budget,
                    temperature=0.0,
                    timeout_seconds=local_timeout,
                )
            except LocalAIRuntimeError as exc:
                low = str(exc).casefold()
                kind = "timeout" if any(x in low for x in ("timeout", "не завершила", "секунд")) else "temporary"
                raise ProviderAPIError(str(exc), kind=kind) from exc
            return str(text).strip(), str(getattr(target, "model", "") or slot.model), str(getattr(target, "label", "") or slot.label)

        raise ProviderAPIError(f"Unknown provider {provider}", kind="configuration")

    def _repair_local_candidate(
        self,
        cfg,
        *,
        prompt: str,
        bad_output: str,
        error: Exception,
        max_output_tokens: int,
    ) -> tuple[str, str, str]:
        repair = (
            "Виправ попередню відповідь так, щоб вона пройшла перевірку нижче. "
            "Не додавай жодних нових фактів, чисел, дат, назв або висновків. "
            "Якщо потрібен JSON, поверни лише валідний JSON без markdown.\n\n"
            f"ПОМИЛКА ПЕРЕВІРКИ: {error}\n\n"
            f"ПОПЕРЕДНЯ ВІДПОВІДЬ:\n{str(bad_output)[:2800]}\n\n"
            f"ПОЧАТКОВЕ ЗАВДАННЯ:\n{_compact_local_prompt(prompt, limit=2600)}"
        )
        text, target = generate_local_text(
            preferred_model=cfg.local_model,
            manual_base_url=cfg.local_base_url,
            manual_model=cfg.local_model,
            prompt=repair,
            max_output_tokens=max(96, min(int(max_output_tokens), self.LOCAL_LONG_MAX_OUTPUT)),
            temperature=0.0,
            timeout_seconds=150,
        )
        return str(text).strip(), str(getattr(target, "model", "") or "local-model"), str(getattr(target, "label", "") or "local")

    def run(
        self,
        prompt: str,
        *,
        validator: Callable[[str], object] | None = None,
        max_output_tokens: int = 800,
        timeout_seconds: int = 25,
        allowed_providers: Iterable[str] | None = None,
    ) -> AIResult:
        text_prompt = str(prompt or "").strip()
        if not text_prompt:
            raise ValueError("Empty AI prompt")
        cfg = load_secrets()
        allowed = None if allowed_providers is None else {str(x).casefold() for x in allowed_providers}
        attempted: list[str] = []
        failures: list[str] = []
        validation_failures = 0
        transport_attempts = 0
        configured: set[str] = set()
        provider_suppressed: set[str] = set()
        # Small editorial gates are JSON tasks. Long writer/final-edit calls remain
        # plain text so no provider-specific JSON mode can corrupt the article body.
        json_mode = validator is not None and int(max_output_tokens) <= 260

        for slot in self._runtime_slots(cfg):
            provider = slot.provider
            if allowed is not None and provider not in allowed:
                continue
            if not self._configured(provider, cfg):
                continue
            configured.add(provider)
            if provider in provider_suppressed or self._provider_blocked(provider):
                continue
            if self._model_blocked(provider, slot.model):
                continue

            attempted.append(f"{provider}:{slot.model}")
            started = time.monotonic()
            lock = self._provider_call_lock(provider)
            wait_for_lock = 6.0 if provider == "local" else min(2.0, max(0.25, float(timeout_seconds) * 0.08))
            acquired = lock.acquire(timeout=wait_for_lock)
            if not acquired:
                failures.append(f"{slot.label}: provider busy")
                event("ai", "provider busy; trying next route", provider=provider, model=slot.model)
                continue
            try:
                try:
                    output, runtime_model, label = self._call_slot(
                        slot,
                        cfg,
                        text_prompt,
                        max_output_tokens=max_output_tokens,
                        timeout_seconds=timeout_seconds,
                        json_mode=json_mode,
                    )
                    transport_attempts += 1
                finally:
                    lock.release()
                if not output:
                    raise ProviderAPIError("Provider returned empty text", kind="bad_response")

                if validator is not None:
                    try:
                        validator(output)
                    except Exception as first_error:
                        validation_failures += 1
                        self._mark_task_failure(provider, runtime_model, first_error)
                        # Local is our last-resort deterministic engine. One bounded
                        # repair turn is cheaper than throwing the article back into
                        # WAITING_AI for another full queue cycle.
                        if provider == "local":
                            try:
                                repaired, repaired_model, repaired_label = self._repair_local_candidate(
                                    cfg,
                                    prompt=text_prompt,
                                    bad_output=output,
                                    error=first_error,
                                    max_output_tokens=max_output_tokens,
                                )
                                validator(repaired)
                                output, runtime_model, label = repaired, repaired_model, repaired_label
                                event("ai", "local candidate repaired", provider="local", model=runtime_model)
                            except Exception as repair_error:
                                failures.append(f"{label}: QA: {first_error}; repair: {repair_error}")
                                event(
                                    "ai", "local candidate rejected after repair", provider="local", model=runtime_model,
                                    elapsed=round(time.monotonic() - started, 2), detail=str(repair_error)[:600],
                                )
                                continue
                        else:
                            failures.append(f"{label}: QA: {first_error}")
                            event(
                                "ai", "candidate rejected by QA", provider=provider, model=runtime_model,
                                elapsed=round(time.monotonic() - started, 2), detail=str(first_error)[:600],
                            )
                            continue

                self._mark_success(provider, slot.model, runtime_model)
                summary = self._refresh_provider_summary(provider, cfg)
                event(
                    "ai", "AI success", provider=provider, model=runtime_model,
                    elapsed=round(time.monotonic() - started, 2), chars=len(output),
                    provider_state=str(summary.state), attempted=len(attempted),
                )
                return AIResult(output, provider, runtime_model, label, tuple(attempted))
            except Exception as exc:
                # lock is already released by the inner finally for call failures.
                failures.append(f"{slot.label}: {exc}")
                state, scope = self._mark_model_failure(provider, slot.model, exc)
                if scope == "provider":
                    provider_suppressed.add(provider)
                event("ai", "route failed", provider=provider, model=slot.model, state=str(state), detail=str(exc)[:600])
                continue

        for provider in configured:
            self._refresh_provider_summary(provider, cfg)
        if not configured:
            raise GatewayExhausted("Не налаштовано жодного AI-провайдера.", retry_seconds=600, provider_outage=True, failures=failures)

        # If at least one engine returned text but every candidate failed article QA,
        # this is a content-quality retry, not a provider outage.
        if validation_failures and transport_attempts:
            raise GatewayExhausted(
                "AI відповів, але кандидати не пройшли редакційний QA. " + " | ".join(failures[-6:]),
                retry_seconds=180,
                provider_outage=False,
                failures=failures,
            )
        raise GatewayExhausted(
            "Тимчасово немає придатного AI-маршруту. " + " | ".join(failures[-6:]),
            retry_seconds=180,
            provider_outage=True,
            failures=failures,
        )

    def _probe_provider(self, provider: str, cfg) -> ProviderHealth:
        if not self._configured(provider, cfg):
            return self._refresh_provider_summary(provider, cfg)

        # Probes intentionally ignore stale model cooldowns. An upgrade/restart is a
        # legitimate opportunity to prove a token/network/model recovered and clear
        # yesterday's state immediately.
        for slot in self._provider_slots(provider, cfg):
            started = time.monotonic()
            lock = self._provider_call_lock(provider)
            if not lock.acquire(timeout=2.0):
                event("ai", "health probe provider busy", provider=provider, model=slot.model)
                continue
            try:
                try:
                    text, runtime_model, _label = self._call_slot(
                        slot,
                        cfg,
                        "Reply with OK only.",
                        max_output_tokens=48 if provider == "local" else 96,
                        timeout_seconds=90 if provider == "local" else 20,
                        json_mode=False,
                    )
                finally:
                    lock.release()
                if not str(text or "").strip():
                    raise ProviderAPIError("health probe returned empty text", kind="bad_response")
                self._mark_success(provider, slot.model, runtime_model, "authenticated completion probe OK")
                event(
                    "ai", "model health probe success", provider=provider, model=runtime_model,
                    elapsed=round(time.monotonic() - started, 2),
                )
                return self._refresh_provider_summary(provider, cfg)
            except Exception as exc:
                _state, scope = self._mark_model_failure(provider, slot.model, exc)
                event(
                    "ai", "model health probe failed", provider=provider, model=slot.model, scope=scope,
                    elapsed=round(time.monotonic() - started, 2), detail=str(exc)[:700],
                )
                if scope == "provider":
                    break
                continue
        return self._refresh_provider_summary(provider, cfg)

    def probe_all(self) -> list[ProviderHealth]:
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
                    current.state = ProviderState.UNKNOWN
                    current.detail = f"health probe crashed: {str(exc)[:900]}"
                    current.updated_at = now_iso()
                    self.store.set_provider_health(current)
                    by_provider[provider] = current
        return [by_provider.get(provider) or self._refresh_provider_summary(provider, cfg) for provider in self.PROVIDER_ORDER]
