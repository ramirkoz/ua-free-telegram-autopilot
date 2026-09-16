# UA FREE Telegram Autopilot v2.0.0-rc44

## READY backlog cleanup and media recovery

RC44 fixes the durable publication backlog exposed by RC43 telemetry.

- READY/PUBLISH rows now obey the channel `max_age_hours` TTL instead of remaining publish candidates forever.
- Stale READY rows are archived safely with `STALE_READY_MAX_AGE`, and any still-active jobs for those rows are closed.
- Startup maintenance immediately removes inherited stale READY backlog after an update.
- Runtime repeats the READY TTL check on the existing one-minute expiration cadence.
- A READY row blocked by recoverable media errors can be unblocked when a later poll supplies genuinely fresh valid media and the publication bundle is complete.
- Ambiguous/partial Telegram delivery states are not auto-cleared by this recovery path.
- Outbound telemetry now reports per-channel `ready_blockers`, `ready_publishable`, and `ready_permanent_blocked` counts so READY stalls are diagnosable remotely.
- RC43 outbound-only observability remains intact; `AgentFeed` and remote commands remain disabled.
- No database schema change. Existing Data, channels, history, feedback and credentials are preserved.
