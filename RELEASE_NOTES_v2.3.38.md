# Autopilot 2.3.38: retired AI model circuit (source-only candidate)

17.11.2026. **DRAFT, not installed.** Based on 2.3.37 source and operator LIVE started 19:48 Kyiv. No official Windows Portable, merge/tag/release.

## Read-only evidence
Live 2.3.37 supervisor: RUNNING 3/3 workers + 3/3 collectors, 34 published today, AI 4/7 healthy, OpenRouter $0.496682 rolling 24h against $3/day. NVIDIA `nvidia/nemotron-3-super-120b-a12b` returns HTTP 410/end of life; older model circuit rechecks it every six hours. Rolling spend spans earlier versions and is not a 2.3.37 cost measure.

## Narrow code change
- `ai_gateway._failure_meta`: HTTP 410 / gone / explicit EOL or no-longer-available response gets a 30-day cooldown scoped to the failed model. Ordinary 404/model-not-found remains six hours. No user-config model deletion, provider-wide ban, source changes or extra AI calls.
- Added unit tests for actual HTTP adapter 410 classification vs 404, 429 and large-context handling. Tests included but not claimed executed.
- Preserve 2.3.37 newsroom voice, 2.3.36 Bored Panda and mass-list exclusions, all fact and media guards, operator Data, 30/30/5, budgets and quarantined Telegram UNKNOWN.

## Open QA gates
- 2.3.37 editorial style: source→final→Telegram review of 5–10 new posts per channel, source fidelity/media checks and 24–48h acceptance still required.
- Historical RC108 nonblocking-media contract conflicts with current intentional `MEDIA_PREWRITE` required-policy holds. Keep unchanged, resolve the policy contradiction explicitly before any media behavioral change.
- Full pytest, independent CI, native Windows/Defender, cost and LIVE QA for v2.3.38 **not verified**. **PRODUCTION GO: NO.** Installed 2.3.37 remains unchanged.
