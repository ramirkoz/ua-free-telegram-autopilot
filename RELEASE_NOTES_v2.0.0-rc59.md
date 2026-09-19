# UA FREE Telegram Autopilot v2.0.0-rc59

RC59 is a throughput-repair release built around a strict separation: universal mechanisms live in runtime code; channel-specific behaviour lives in channel settings.

- Hardens scientific-name extraction: a Latin-looking pair is accepted only with nearby taxonomy evidence.
- Hardens entity fingerprints: ordinary sentence-start/title words no longer become named entities from capitalization alone.
- Hardens compound-event dedupe: rare-word overlap alone cannot normally collapse two stories without an independent identity/fact anchor.
- Adds channel-owned output-starvation policy (`enabled`, `hours`, `min_processed`) and a universal `CHANNEL_OUTPUT_STARVATION_<id>` Supervisor incident.
- Uses the existing per-channel `editorial_weights_json` setting for optional editorial threshold overrides. No channel names or IDs are consulted at runtime.
- Existing explicit profiles are migrated once to sensible RC59 settings by profile/mode, never by channel name or ID.
- Preserves RC58 UA Anti-Slop, BOM-safe updater, signed update verification, DB backup, runtime health proof and rollback.
