# UA FREE Telegram Autopilot 2.0.0-rc114

RC114 makes feedback/statistics learning unattended and operator-visible.

## Automatic refresh
- Default feedback refresh interval changes from 15 minutes to **3 hours**.
- The interval is configurable from the Statistics / Learning tab without rebuilding the application.
- Allowed operator range is 15 minutes to 24 hours.
- The selected interval is persisted in the V2 database.

## UI synchronization
- A successful background feedback cycle automatically refreshes the Statistics / Learning view.
- The UI shows:
  - configured interval;
  - last successful automatic refresh;
  - next refresh countdown;
  - last automatic refresh error.
- Manual "Update statistics", seven-day refresh and single-publication refresh remain available.

## Runtime isolation
- Feedback collection remains a separate background worker.
- Telegram Analytics failure never blocks collection, AI processing or publication.
- Automatic refresh emits explicit feedback telemetry for success/degraded state and interval changes.

## Preserved RC113 contracts
- page-level hero recovery and media diagnostics;
- RC112 source integrity, galleries, required media and video handling;
- source cooldown, QUALITY and delivery contracts.

## Live acceptance
1. telemetry reports version=2.0.0-rc114;
2. automatic statistics refresh runs without pressing the manual button;
3. UI reflects refreshed values after the background cycle;
4. selected interval survives restart;
5. feedback failure does not stop workers/collectors/publication;
6. RC113 media/source-integrity behavior does not regress.

Next:
- RC115: full OpenRouter provider;
- then 2.0.0 stable after acceptance.
