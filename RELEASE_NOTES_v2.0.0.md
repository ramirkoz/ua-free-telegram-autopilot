# UA FREE Telegram Autopilot 2.0.0 stable

Stable promotion is intentionally feature-frozen on top of RC115.

## Inherited release contracts
- RC113 native web-media recovery, gallery/video handling and source binding.
- RC114 unattended feedback/statistics refresh with configurable interval and UI state.
- RC115 opt-in OpenRouter provider with encrypted key, reviewed model allow-list, reserve routing, health/cooldown, actual provider-reported cost telemetry and 24h/monthly budgets.
- Delivery journal, QUALITY retry controls, source health/cooldown and dedupe behavior remain unchanged.

## Promotion gates
2.0.0 stable may be merged/tagged/released only when all are true:
1. Canonical RC115 runtime reports healthy workers/collectors and no P0/P1.
2. RC113 media/source-integrity live checks remain green.
3. RC114 automatic feedback/statistics refresh is observed without manual action.
4. OpenRouter disabled path is confirmed absent from production routing.
5. OpenRouter enabled path is live-probed with a valid operator key and reviewed model ID, with token usage and actual cost recorded.
6. OpenRouter budget exhaustion is proven not to block other providers.
7. Overnight runtime completes with no P0/P1.
8. Full regression/Windows release/Defender gates pass.
9. GitHub release assets, Drive CURRENT and ProductVault canonical files are synchronized.

## Version rule
Do not create RC116 for normal stabilization. The next canonical version after accepted RC115 is exactly `2.0.0`.
