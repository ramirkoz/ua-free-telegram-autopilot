"""2.2.63: ephemeral model-specific bad-output contract circuit.

LIVE: Ling/OpenRouter and GLM/Cloudflare sometimes return reasoning without
final content; Ollama sometimes stalls for 120 seconds. Two exact failures
within ten minutes temporarily defer ONLY that provider/model. Another healthy
model on the SAME provider remains available. No DB or operator config changes,
no background timers, no new AI requests, no permanent provider quarantine.
"""
from __future__ import annotations

import time


class RouteContractCircuit:
    def __init__(self):
        self._events: dict[tuple[str, str], tuple[int, float, float]] = {}

    def remaining(self, provider: str, model: str, *, now: float | None = None) -> float:
        stamp = time.monotonic() if now is None else float(now)
        key = (str(provider).lower(), str(model).lower())
        state = self._events.get(key)
        if state is None:
            return 0.0
        count, last, until = state
        if stamp >= until and stamp - last > 600:
            self._events.pop(key, None)
            return 0.0
        return max(0.0, until - stamp)

    def note_failure(self, provider: str, model: str, error: Exception, *,
                     now: float | None = None) -> bool:
        p = str(provider or "").lower()
        message = str(error or "").lower()
        kind = str(getattr(error, "kind", "") or "").lower()
        reasoning = (
            p in {"openrouter", "cloudflare"}
            and kind == "bad_response"
            and "reasoning but no final content" in message
        )
        cpu_timeout = p == "local" and (
            kind == "timeout" or "не завершила локальне ai-завдання за 120 секунд" in message
        )
        oversized_writer = (p == "groq" and "http 413" in message)
        if not (reasoning or cpu_timeout or oversized_writer):
            return False
        stamp = time.monotonic() if now is None else float(now)
        key = (p, str(model or "").lower())
        count, last, until = self._events.get(key, (0, 0.0, 0.0))
        if stamp - last > 600:
            count = 0
        count += 1
        if count >= 2:
            until = stamp + (900 if cpu_timeout else 600 if reasoning else 300)
        self._events[key] = (count, stamp, until)
        return count >= 2

    def clear(self, provider: str, model: str) -> None:
        self._events.pop((str(provider or "").lower(), str(model or "").lower()), None)
