# UA FREE Telegram Autopilot v2.0.0-rc40

## Local-only supervision

RC40 mirrors the proven KONTUR RC40 supervision model.

- Remote Supervisor AgentFeed execution is disabled.
- Remote review requests, agent journals, hourly agent feed files and the agent-check Telegram bridge are no longer active runtime paths.
- Passive Drive mirroring of supervisor status/incidents is disabled; the LIVE folder remains available only for the narrow signed updater protocol.
- Local runtime/database/AI/queue/media health checks remain enabled.
- A local Telegram reporter sends compact status directly from the running application and reports incident-state changes without any remote agent.
- The signed RC37+ external updater, health gate and rollback remain enabled and unchanged.
- RC39 Codex reset-aware cooldowns, CPU-only Ollama tuning and duplicate-safe update request selection remain intact.

No Data migration is required.
