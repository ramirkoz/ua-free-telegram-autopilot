# UA FREE Telegram Autopilot V2 2.0.0-rc30

RC30 adds the durable Supervisor Agent → Telegram status bridge requested for remote supervision.

## Changes

- The remote Supervisor Agent can drop `agent_telegram_report.json` into the canonical LIVE feed.
- Local Autopilot consumes that report and sends the compact status through the configured Telegram bot.
- Delivery is replay-safe by `report_id` and confirmed with `agent_telegram_ack.json` only after Telegram returns a message ID.
- Telegram target resolution is conservative: explicit report target, environment target, local/Drive `agent_telegram_target.json`, cached target, or exactly one private Bot API chat discovered via `getUpdates`.
- Multiple private chats are never guessed.
- Retry cooldown prevents 30-second resend storms after configuration/network failures.
- Existing Data, SQLite, channel settings, publication pipeline and editorial/media rules are unchanged.

## Validation

Regression coverage includes exactly-once delivery, restart replay protection, single-private-chat discovery, ambiguous-target refusal, and safe bot-token selection.
