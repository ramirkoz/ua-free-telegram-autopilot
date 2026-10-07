# UA FREE Telegram Autopilot 2.0.0 stable

Stable promotion is intentionally feature-frozen on top of RC115.

## Inherited release contracts
- RC113 native web-media recovery, gallery/video handling and source binding.
- RC114 unattended feedback/statistics refresh with configurable interval and UI state.
- RC115 opt-in OpenRouter provider with encrypted key, reviewed model allow-list, reserve routing, health/cooldown, actual provider-reported cost telemetry and 24h/monthly budgets.
- Delivery journal, QUALITY retry controls, source health/cooldown and dedupe behavior remain unchanged.

## Promotion gates

Operator decision on 2026-10-07: OpenRouter remains an optional provider and is intentionally left disabled for the stable promotion. Its enabled-path live test does not block 2.0.0.

Required for stable:
1. RC113 media/source-integrity contracts remain green.
2. RC114 feedback/statistics automation remains present and non-blocking.
3. RC115 OpenRouter disabled path remains absent from routing by default.
4. Full regression/Windows release/Defender gates pass.
5. GitHub release assets, Drive CURRENT and ProductVault canonical files are synchronized.

The already-running RC115 portable remains on overnight soak separately. Any overnight P0/P1 discovered there blocks acceptance of the deployed stable build, but does not require inventing RC116 unless code changes are actually needed.

## Version rule
Do not create RC116 for normal stabilization. The next canonical version after accepted RC115 is exactly `2.0.0`.
