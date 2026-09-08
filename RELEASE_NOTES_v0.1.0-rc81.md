# UA FREE Telegram Autopilot v0.1.0-rc81

- Codex now starts with explicit model `gpt-5.4` (`UA_FREE_CODEX_MODEL` may override it), so a stale account/default model cannot silently route production into a dead `gpt-5.5` backend.
- Persistent circuit breakers stop hot-loop retries: model-not-found 404 = 7 days, Codex state/config failure = 6 hours, network failure = at least 15 minutes, HTTP 503 = at least 5 minutes, local AI timeout = 30 minutes.
- Global provider outages are normalized to the existing `Немає доступного AI-провайдера` path, so the current service stops that processing cycle instead of walking the whole fresh queue into identical failures.
- RC67 preparation pauses while every configured provider is on cooldown; fresh articles stay pending and resume automatically when any provider becomes healthy.
- Provider-outage article retries are bounded: 5 minutes, 30 minutes, 2 hours, then terminal error instead of five rapid overnight attempts.
- RC80 cluster repair is throttled to at most 20 recent rows per application start and enters the retry queue rather than the hot `new` queue.
- RC81 recovers at most 30 newest outage-caused rows from the last 24 hours and staggers them by two minutes.
- RC80 strict same-event dedupe and all RC79 monitoring/media/contact/source-link fixes remain active.
