# UA FREE Telegram Autopilot v2.0.0-rc80

Manual-test release focused on Codex recovery and channel-scoped source attribution.

- Adds an explicit “Встановити / оновити Codex” action on the AI tab. The current openai-codex 0.156.1 runtime is installed into portable-root Tools\Codex and can be used immediately after installation.
- Keeps Codex opt-in: RC80 does not silently download the SDK on application startup.
- Moves source attribution inside the post body into visible per-channel policy data.
- Adds three body-attribution modes: footer-only, always allow, or allow only when source_name contains the channel-configured marker.
- The runtime is marker-agnostic. Channel-specific marker values are stored in channel policy, not in editorial/source-attribution logic.
- Deterministic QA blocks source-name/alias mentions in the post body when the selected channel policy forbids body attribution.
- Existing named-source channels receive a one-time compatibility migration that persists the previous hidden marker behavior as editable channel settings.
