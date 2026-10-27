# Autopilot 2.2.40 — commercial publishing yield instead of raw feed intake

## Why this release exists
2026-10-27 09:55 Kyiv operator LIVE v2.2.39: all 3 workers/collectors healthy, 772 COMMITTED, only 5 commercial posts today, zero in last 30 minutes. Last commercial 24h cohort: 139 processed, 13 published, 118 rejected. Source diagnostics: **Muse by Clio** 23 discovered /0 published (22 rejected), **Campaigns of the World** 10/0, **Yanko Design** 16/6, **Creative Bloq** 6/4. The 2.2.37 source scheduler used `last_added` to favor *intake*, accidentally rewarding feeds with near-100% editorial rejection and short excerpts.

## Actual changes in 2.2.40
1. Commercial collector still fetches the SAME approved sources (18) under operator cooldowns and original source priorities, but uses each source's *actual published results in the last 24h* as a bounded scheduling hint, rather than assuming more raw additions are valuable. Up to 12 priority points of publication bonus and mild rejection penalties. Recently successful narrow streams (Yanko/Creative Bloq) start earlier; those with lots of short snippets/policy rejects are polled later, **never skipped or disabled**. All other channels unchanged.
2. A read-only source-cohort query counts exact `EDITORIAL_MIN_TWO_SENTENCES: source` failures separately. Existing `commercial_source_funnel_24h` supervisor / Drive now exposes `short_source_rejected_24h` per source and summary. That makes it possible to distinguish weak fit from insufficient original facts without guessing or weakening the source-two-sentence factual floor.
3. Regression suite includes real SQLite per-channel 24h published/short-source cohort with a source at 23 additions/0 publications vs 6 additions/4 publications; confirms correct ordering, older publications excluded, cross-channel isolation and that no operator cooldown/source/DB article changes occur.

## Known not fixed
- This release does **not** automatically expand one-sentence headlines to two sentences or invent unsupported facts. Short source excerpts remain rejected until authoritative full source is available. It does not grant publishing rights to anything below existing commercial editorial quality gates.
- The external HTTP 403 from Design Milk or Rest of World isn't solved by bypassing anti-bot measures; replacement or official feed requires operator approval. Shots, Creative Boom and Ad Age may still time out; the existing protected 70s collector timeout/cooldowns remain unchanged.
- Unverified nearby Telegram photos remain unbound. Existing delivery anti-duplication including UNKNOWN #66297 unchanged.

## Version compatibility / operator acceptance
- No changes to DB schema, source enabled flags or list, interval 45/30/5 min, OpenRouter $3/day/$20/month, AI credentials or independent `autopilot-oauth` Drive service, existing Data or receipt integrity.
- Gate: PR full 4/4 CI, Windows native portable startup, Microsoft Defender; after merge main 4/4 CI and native Windows release SUCCESS, official GitHub tagged ZIP with SHA256.
- Back up **whole Data**, stop 2.2.39, unzip official Windows 2.2.40 portable in a separate folder, transfer Data unchanged, start only ONE instance, retain prior folder for rollback.
- Verify actual v2.2.40 in LIVE (not just archive created): 3/3 workers+collectors, independent Drive, 772+ COMMITTED, no duplicate replay, per-source `short_source_rejected_24h` exists for commercial, source roster counts 36/18/57, channel intervals, budgets, publication yield measured over multiple collection cycles. Don't claim throughput improvement from a short heartbeat alone.
