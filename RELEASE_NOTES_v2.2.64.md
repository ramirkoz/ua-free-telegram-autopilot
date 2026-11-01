# Autopilot v2.2.64 — new commercial article discovery and source mix

**01.11.2026.** Release candidate. GitHub PR/CI and official Windows publication are separate gates; LIVE operator acceptance remains pending.

## Verified 2.2.63 operator evidence
- RUNNING 3/3 workers and collectors at 16:04 Kyiv. Telegram deliveries retained; one historical UNKNOWN protected.
- Commercial publisher listings return KNOWN_ONLY/EMPTY; no newly ingested post-v63 commercial article yet. Yanko Design accounts for 33/50 (66%) published commercial posts in seven days.
- 24h commercial pipeline has many rejected weak/general B2B stories. Do not relax the reader-first threshold just to fill the schedule.

## Changes
1. **Existing commercial PAGE sources:** known URL links are filtered **before** the configured new-candidate scan cap, using a bounded wider listing window (48–160 link checks, depending on operator scan limit). Previously, high-scoring known links could consume the window and hide lower-ranked new original stories. Hydration cap and source deadline unchanged.
2. **Original-source diversity:** the current editorial selector receives a soft, per-source seven-day concentration reminder when a candidate's original source accounts for at least 60% of at least 20 real posts from at least two sources, including lexical “other” stories. This asks for a unique evidenced reader hook, but introduces **no ban, quota, auto-reject, new AI request, or source disable**.
3. No source URLs, operator Data, Telegram receipts, historical UNKNOWN safety, per-channel intervals, source-authored timestamps, media or existing editorial thresholds changed.

## Acceptance gates
- Targeted test_2264_* files, existing suites, PR Ubuntu + Windows CI and Portable/Defender.
- Operator installs with unchanged Data, then confirms new source-owned article timestamps and actual added > 0 from eligible publisher listings, followed by real publications, plus seven-day source mix. KNOWN_ONLY is **not** success.
- Final 90–100 natural posts SOURCE→FINAL→Telegram audit remains for v2.3.0.
