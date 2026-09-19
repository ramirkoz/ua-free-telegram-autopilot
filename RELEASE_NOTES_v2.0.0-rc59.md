# UA FREE Telegram Autopilot v2.0.0-rc59

RC59 repairs channel throughput while enforcing a strict architecture boundary:
universal mechanisms stay in the runtime; channel-specific behavior is stored in channel settings.

## Universal runtime fixes

- Scientific-name event matching now requires a plausible Latin binomial and local scientific context.
- Common English phrase pairs such as “American hope”, “Astra model”, “Great science”, “Quickly podcast” and “Subscriptions keep” are not accepted as taxa.
- Compound-event thresholds are configurable by the channel rather than hardcoded for a named channel.
- Commercial editorial value lanes use per-channel threshold JSON instead of fixed product-specific behavior.
- Supervisor adds universal CHANNEL_OUTPUT_STARVATION_<channel_id> detection.

## Channel settings

New persisted and visible per-channel settings:
- dedupe_settings_json
- editorial_value_settings_json
- output_starvation_enabled
- output_starvation_hours
- output_starvation_min_processed

A one-time compatibility migration initializes these values from already persisted mode/profile settings only. Runtime behavior never branches on channel ID or name.

## Preserved

- RC58 UA Anti-Slop v1
- RC58 BOM-safe autonomous updater
- RC57 channel-configured dedupe/editorial profiles
- signed update SHA verification, backup, health proof and rollback
- existing Data/DB/history/feedback/credentials
