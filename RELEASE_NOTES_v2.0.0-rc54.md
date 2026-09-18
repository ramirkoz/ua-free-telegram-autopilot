# UA FREE Telegram Autopilot v2.0.0-rc54

Stability/editorial hotfix deployed through the signed Drive remote-update path.

- Fixes RC52/RC53 false source cooldown storm: per-source rolling scheduler, no channel-wide 70 s timer for queued sources.
- Automatically clears cooldowns created specifically by the old false `channel budget` timeout.
- Enforces existing `topic_balance_enabled`, `topic_daily_limit`, and `related_spacing_posts` against published history to stop monitoring-topic floods.
- Preserves practical monitoring URLs, email addresses, and phone numbers deterministically after AI rewriting.
- Adds a dedicated `ПРОДАНО!` commercial-value gate and normalizes contradictory `publish` + very-low-fit model output.
- Ignores stale Drive update requests whose target is not newer than the installed runtime.
- Keeps RC53 entity/fact event dedupe and seven-day pre-publish duplicate protection.
