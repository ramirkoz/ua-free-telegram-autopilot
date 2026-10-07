# UA FREE Telegram Autopilot 2.0.0-rc115

RC115 adds OpenRouter as a full, explicitly controlled AI provider.

## Operator control
- OpenRouter is disabled by default.
- API key is stored in the existing encrypted secrets store.
- The AI tab now has an explicit enable/disable switch.
- Operators provide an allow-list of reviewed OpenRouter model IDs.
- Models discovered in the OpenRouter catalog never become unattended production routes automatically.
- A live OpenRouter health test is available from the UI.

## Routing
- OpenRouter participates in normal provider/model health and cooldown handling.
- It is intentionally a paid reserve behind reviewed direct/free routes.
- Up to 12 explicitly configured OpenRouter models may be available to the router.
- Existing direct Gemini/NVIDIA/Groq/Cloudflare/local/Codex routes remain independent.

## Cost telemetry and budgets
- OpenRouter requests ask the provider to return usage data.
- Actual OpenRouter spend is persisted separately from the existing reference-price estimate.
- Telemetry exposes:
  - actual OpenRouter spend in the last 24 hours;
  - actual calendar-month spend;
  - configured daily and monthly caps;
  - selected model allow-list.
- Daily and monthly budget caps fail closed: once the cap is reached, OpenRouter is skipped while the rest of the AI router continues normally.
- A budget value of 0 means no cap.

## UI
OpenRouter settings include:
- enable/disable;
- encrypted API key;
- comma-separated reviewed model allow-list;
- 24-hour budget;
- monthly budget;
- save;
- live provider test;
- current spend/status.

## Database migration
Existing V2 databases receive the new actual OpenRouter cost column without losing prior AI usage rows.

## Preserved contracts
RC115 preserves:
- RC114 automatic statistics/learning refresh;
- RC113 native web-media recovery and diagnostics;
- RC112 source integrity, required-media semantics and gallery/video handling;
- source health/cooldown, QUALITY and delivery controls.

## Acceptance
1. telemetry reports version=2.0.0-rc115;
2. OpenRouter remains absent from routing while disabled;
3. enabling with a valid key and reviewed model produces HEALTHY after a live probe;
4. successful calls report token usage and actual OpenRouter cost;
5. daily/monthly budget exhaustion prevents new OpenRouter calls without blocking other providers;
6. OpenRouter never outranks the same reviewed direct model;
7. RC113/RC114 media/source/statistics behavior does not regress;
8. no P0/P1 during the live/overnight run.

If RC113-RC115 acceptance passes, the next target is 2.0.0 stable.
