UA FREE Telegram Autopilot v2.0.0-rc80 — MANUAL TEST

RC80:
- Codex SDK can be installed/updated explicitly into Tools\Codex from the AI tab.
- Source attribution inside post body is controlled only by visible per-channel settings.
- Conditional marker mode allows body attribution only when source_name contains the configured marker; otherwise source stays in footer only.
- Core runtime contains only the generic attribution mechanism; channel-specific marker values live in channel policy data.
