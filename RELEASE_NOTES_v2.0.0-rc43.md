# UA FREE Telegram Autopilot v2.0.0-rc43

## Outbound-only telemetry without the remote agent

RC43 restores live observability after the RC41 local-only transition without bringing the remote maintenance agent back.

- `AgentFeed` remains disabled and is never constructed.
- Remote commands, review requests, agent journals/hourly feeds and the agent Telegram bridge remain disabled.
- The Supervisor mirrors only three passive files to the synced LIVE folder: `status.json`, `recent_events.json` and `incident.json`.
- The telemetry path is outbound-only; these files are never consumed as commands.
- The only inbound control path remains the signed updater protocol with post-update health validation and rollback.
- Telemetry mirror discovery/self-healing and stale/mirror-error health checks are active again.
- The final snapshot for each tick is re-mirrored after the local Telegram report result is attached.
- RC42 throughput fixes remain unchanged: local Ollama is short-task-only, long-form generation stays off CPU fallback, circuit breakers and slow-source cooldowns remain active.
- No database schema change; existing Data, channels, history, feedback and credentials are preserved.
