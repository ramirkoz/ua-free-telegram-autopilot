# UA FREE Telegram Autopilot v2.0.0-rc41

## Remote agent fully disabled

RC41 completes the local-only supervision transition.

- The remote AgentFeed object is never constructed.
- Remote review requests, agent journals, hourly agent feed files and the agent-check Telegram bridge remain disabled.
- Local Supervisor health checks remain active.
- Local Telegram operational reporting remains active.
- Signed self-update, post-update health validation and rollback remain active.
- No database schema change.
- Existing Data, channels, history, feedback and credentials are preserved.
