# UA FREE Telegram Autopilot v2.0.0-rc39

## Autonomous AI cooldowns and Drive-safe updates

RC39 hardens unattended operation after the first successful RC37 → RC38 remote update.

- Codex usage-limit responses now parse the advertised reset timestamp and keep the provider asleep until that reset instead of probing it repeatedly.
- Provider summaries expose the active model cooldown so UI and supervisor telemetry show when a model is intentionally paused.
- Startup/manual provider probes respect model cooldowns.
- The CPU-only Ollama fallback is tuned further for the production notebook with 24 GB RAM and no discrete GPU: prompts are compacted, local output is bounded, only one local generation runs at a time, and timeout recovery uses a longer cooldown instead of immediately hammering the model again.
- Local fallback keeps cloud providers preferred when they are healthy, while remaining usable when cloud quotas are exhausted.
- Remote update intake scans synced `update_request*.json` variants and chooses the newest/highest validated target, so Google Drive duplicate-name conflicts cannot hide an approved release.
- Regression tests cover Codex reset parsing, long quota cooldowns, bounded local prompts and duplicate Drive update requests.

All RC38 CPU-only recovery, RC37 external update/rollback transaction, Telegram reporting, source attribution and RC36 media fail-closed behavior remain intact.
