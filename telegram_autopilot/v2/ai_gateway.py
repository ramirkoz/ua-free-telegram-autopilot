from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable

from .. import ai_router as legacy_ai
from ..codex_engine import CodexEngineError, run_codex
from ..local_ai_runtime import LocalAIRuntimeError, generate_local_text
from ..secrets_store import load_secrets
from .domain import BlockedBy, ProviderHealth, ProviderState
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
        if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc) > datetime.now(timezone.utc)
    except Exception:
        return False


def _classify(exc: Exception) -> tuple[ProviderState,int]:
    kind = str(getattr(exc,"kind","") or "").casefold()
    text = str(exc).casefold()
    if kind == "auth" or any(x in text for x in ("unauthorized","forbidden","invalid api key","ключ або доступ відхилено")):
        return ProviderState.AUTH_ERROR, 1800
    if kind == "quota" or "quota" in text or "ліміт" in text or "429" in text:
        return ProviderState.QUOTA, 300
    if kind in {"gone","model"} or any(x in text for x in ("model unsupported","model_not_found","модель більше недоступна")):
        return ProviderState.MODEL_UNSUPPORTED, 60
    if kind == "configuration":
        return ProviderState.CONFIG_ERROR, 900
    if kind == "network" or any(x in text for x in ("network request failed","connection","dns","name resolution")):
        return ProviderState.NETWORK_DOWN, 120
    if "timeout" in text or "timed out" in text or "не завершила" in text:
        return ProviderState.TIMEOUT, 90
    return ProviderState.NETWORK_DOWN, 90


class AIGateway:
    """Single source of truth AI gateway for V2.

    The provider HTTP/Codex primitives are reused from the canonical non-RC modules,
    but V2 never calls their historical router/cooldown machinery. Health lives only
    in V2 ``provider_health`` and is consumed by workers, scheduler and UI.
    """

    PROVIDER_ORDER = ("codex","gemini","nvidia","groq","cloudflare","local")

    def __init__(self, store: V2Store):
        self.store = store

    def _health_map(self) -> dict[str,ProviderHealth]:
        return {item.provider:item for item in self.store.provider_health()}

    def _configured(self, provider: str, cfg) -> bool:
        if provider == "codex":
            try: return bool(legacy_ai._codex_configured_cached())
            except Exception: return True
        if provider == "gemini": return bool(cfg.gemini_api_key)
        if provider == "nvidia": return bool(cfg.nvidia_api_key)
        if provider == "groq": return bool(cfg.groq_api_key)
        if provider == "cloudflare": return bool(cfg.cloudflare_account_id and cfg.cloudflare_api_token)
        if provider == "local": return bool(cfg.local_enabled)
        return False

    def _slots(self, provider: str, cfg) -> list[legacy_ai.Slot]:
        reviewed = [s for s in legacy_ai._runtime_model_slots(cfg) if s.provider == provider]
        if provider not in {"gemini","nvidia","groq"}:
            return reviewed
        try:
            discovered = legacy_ai._discover_provider_model_ids(provider,cfg,force=False)
        except Exception:
            discovered = ()
        existing = {s.model for s in reviewed}
        base_priority = (max((s.priority for s in reviewed), default=100) + 1)
        family = "gemini" if provider == "gemini" else "openai"
        for index, model in enumerate(discovered[:3]):
            if model in existing: continue
            reviewed.append(legacy_ai.Slot(base_priority+index,provider,model,f"{model} / {provider}",family))
        return sorted(reviewed,key=lambda x:x.priority)

    def _mark_success(self, provider: str, model: str, detail: str = "") -> None:
        current = self._health_map().get(provider,ProviderHealth(provider=provider))
        restored = current.state != ProviderState.HEALTHY
        current.state=ProviderState.HEALTHY; current.model=model; current.detail=detail
        current.consecutive_failures=0; current.success_count+=1; current.cooldown_until=""; current.updated_at=now_iso()
        self.store.set_provider_health(current)
        if restored:
            woke=self.store.wake_blocked(BlockedBy.AI,limit=20)
            event("ai","provider restored",provider=provider,model=model,woke_waiting_ai=woke)

    def _mark_failure(self, provider: str, model: str, exc: Exception) -> ProviderState:
        state,seconds=_classify(exc)
        current=self._health_map().get(provider,ProviderHealth(provider=provider))
        current.state=state; current.model=model; current.detail=str(exc)[:1200]
        current.consecutive_failures+=1; current.failure_count+=1
        current.cooldown_until=(datetime.now(timezone.utc)+timedelta(seconds=seconds)).astimezone().isoformat(timespec="seconds")
        current.updated_at=now_iso(); self.store.set_provider_health(current)
        event("ai","provider failure",provider=provider,model=model,state=str(state),detail=str(exc)[:600],cooldown_seconds=seconds)
        return state

    def _call_slot(self, slot: legacy_ai.Slot, cfg, prompt: str, *, max_output_tokens: int, timeout_seconds: int) -> str:
        if slot.provider == "codex":
            return str(run_codex(prompt)).strip()
        if slot.provider == "gemini":
            return str(legacy_ai._gemini(slot,cfg,prompt,max_output_tokens=max_output_tokens,timeout_seconds=timeout_seconds)).strip()
        if slot.provider in {"nvidia","groq","cloudflare"}:
            return str(legacy_ai._openai(slot,cfg,prompt,max_output_tokens=max_output_tokens,timeout_seconds=timeout_seconds)).strip()
        if slot.provider == "local":
            text,target=generate_local_text(
                preferred_model=cfg.local_model,manual_base_url=cfg.local_base_url,manual_model=cfg.local_model,
                prompt=prompt,max_output_tokens=max_output_tokens,temperature=0.0,timeout_seconds=max(8,timeout_seconds),
            )
            return str(text).strip()
        raise RuntimeError(f"Unknown provider {slot.provider}")

    def run(self, prompt: str, *, validator: Callable[[str],object] | None = None, max_output_tokens: int = 800,
            timeout_seconds: int = 25, allowed_providers: Iterable[str] | None = None) -> AIResult:
        text_prompt=str(prompt or "").strip()
        if not text_prompt: raise ValueError("Empty AI prompt")
        cfg=load_secrets(); allowed=None if allowed_providers is None else {str(x).casefold() for x in allowed_providers}
        health=self._health_map(); attempted:list[str]=[]; failures:list[str]=[]; validation_failures=0; configured_count=0
        for provider in self.PROVIDER_ORDER:
            if allowed is not None and provider not in allowed: continue
            if not self._configured(provider,cfg): continue
            configured_count+=1
            current=health.get(provider)
            if current and current.state in {ProviderState.AUTH_ERROR,ProviderState.QUOTA,ProviderState.NETWORK_DOWN,ProviderState.TIMEOUT,ProviderState.CONFIG_ERROR} and _cooldown_active(current.cooldown_until):
                continue
            slots=self._slots(provider,cfg)
            if provider == "codex" and not slots:
                slots=[legacy_ai.Slot(0,"codex","account-default","Codex / ChatGPT","codex")]
            if provider == "local" and not slots:
                slots=[legacy_ai.Slot(999,"local",str(cfg.local_model or "local-model"),"Локальний AI","local")]
            provider_model_failure=False
            for slot in slots:
                attempted.append(f"{provider}:{slot.model}"); started=time.monotonic()
                try:
                    output=self._call_slot(slot,cfg,text_prompt,max_output_tokens=max_output_tokens,timeout_seconds=timeout_seconds)
                    if not output: raise RuntimeError("Провайдер повернув порожню відповідь")
                    if validator is not None:
                        try: validator(output)
                        except Exception as exc:
                            validation_failures+=1; failures.append(f"{slot.label}: QA: {exc}")
                            event("ai","candidate rejected by QA",provider=provider,model=slot.model,elapsed=round(time.monotonic()-started,2),detail=str(exc)[:500])
                            continue
                    self._mark_success(provider,slot.model)
                    event("ai","AI success",provider=provider,model=slot.model,elapsed=round(time.monotonic()-started,2),chars=len(output))
                    return AIResult(output,provider,slot.model,slot.label,tuple(attempted))
                except Exception as exc:
                    # Editorial validators are handled above. Everything here is transport/runtime/provider failure.
                    failures.append(f"{slot.label}: {exc}"); state=self._mark_failure(provider,slot.model,exc)
                    provider_model_failure=True
                    # Model-specific failure: immediately try the next candidate for the same provider.
                    if state == ProviderState.MODEL_UNSUPPORTED: continue
                    # Quota/auth/network is provider-level for this iteration; move on to fallback provider.
                    break
            if provider_model_failure:
                continue
        if configured_count == 0:
            raise GatewayExhausted("Не налаштовано жодного AI-провайдера.",retry_seconds=600,provider_outage=True,failures=failures)
        # If at least one model answered but every answer failed article-specific QA, provider health is not the problem.
        if validation_failures and validation_failures >= len(attempted):
            raise GatewayExhausted("AI відповів, але всі кандидати відхилені редакційним QA. "+" | ".join(failures[-5:]),retry_seconds=180,provider_outage=False,failures=failures)
        raise GatewayExhausted("Тимчасово немає придатного AI-маршруту. "+" | ".join(failures[-5:]),retry_seconds=180,provider_outage=True,failures=failures)

    def probe_all(self) -> list[ProviderHealth]:
        cfg=load_secrets(); result=[]
        for provider in self.PROVIDER_ORDER:
            if not self._configured(provider,cfg):
                health=ProviderHealth(provider=provider,state=ProviderState.CONFIG_ERROR,detail="не налаштовано",updated_at=now_iso())
                self.store.set_provider_health(health); result.append(health); continue
            slots=self._slots(provider,cfg)
            if provider == "codex" and not slots: slots=[legacy_ai.Slot(0,"codex","account-default","Codex / ChatGPT","codex")]
            if provider == "local" and not slots: slots=[legacy_ai.Slot(999,"local",str(cfg.local_model or "local-model"),"Локальний AI","local")]
            last:ProviderHealth|None=None
            for slot in slots:
                try:
                    text=self._call_slot(slot,cfg,"Reply with OK only.",max_output_tokens=32,timeout_seconds=15)
                    if not text: raise RuntimeError("empty health response")
                    self._mark_success(provider,slot.model,"health probe OK")
                    last=self._health_map()[provider]; break
                except Exception as exc:
                    self._mark_failure(provider,slot.model,exc); last=self._health_map()[provider]
                    if last.state != ProviderState.MODEL_UNSUPPORTED: break
            result.append(last or ProviderHealth(provider=provider,state=ProviderState.UNKNOWN,updated_at=now_iso()))
        return result
