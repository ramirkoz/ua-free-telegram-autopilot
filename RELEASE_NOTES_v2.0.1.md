# UA FREE Telegram Autopilot 2.0.1

2.0.1 is the stabilization release after 2.0.0.

## Included
- Night-telemetry source-health fixes: real items/added accounting and KNOWN_ONLY instead of false EMPTY cooldown.
- Durable delivery-journal truth for MEDIA_LOST_ON_PUBLISH.
- Feedback auto-refresh visibility in telemetry/supervisor.
- OpenRouter UX aligned with Content Tool:
  - no mandatory manual model IDs;
  - automatic live model-catalog selection;
  - economy / balanced / quality strategy;
  - enable/disable and budget controls retained;
  - manual model list remains compatibility/advanced override only.
- Updater version ordering generalized for 2.0.1 and future semver releases.

## OpenRouter
OpenRouter remains optional and disabled by default. When enabled with an API key, Autopilot retrieves the live model catalog and selects suitable text models automatically according to strategy, quality, context size and price.

## Acceptance
Full Ubuntu/Windows regression, migration/live-source/media gates, Defender, exact portable, Drive CURRENT and ProductVault synchronization are required.
