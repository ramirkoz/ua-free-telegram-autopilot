# UA FREE Telegram Autopilot v2.3.28 · operator acceptance candidate

**Status: TEST CANDIDATE. Not installed. Not approved for deployment.**

## Changes implemented
- Windows channel settings now have a fixed, visible Save/Cancel footer with a scrollable form in all six tabs; dirty state, confirmation before closing, persisted readback and runtime refresh callback. No hidden-tab workarounds.
- Media safety: article parser excludes Creative Bloq common “Gear up” retail/product section, expands global ecommerce-context filters, and rejects empty-evidence CSS gallery assets without verified article ownership. Regression case: Creative Bloq Naruto #961 / article 97460, plus prior #934.
- Publication safety: fail-closed check rejects texts ending in unfinished punctuation or conjunction (e.g. CTRL #1854 ended with colon); bounded quality rewrite, not fabricated completion.
- Restart safety: same-day READY prepared before a short restart can cross runtime-start fence after durable Telegram delivery preflight, but stale/previous-day/unknown delivery remains blocked.
- Version metadata synchronized to 2.3.28 and focused Python tests added.

## Must be verified before operator rollout
- Windows CI, runtime launch smoke, all six settings tabs at 1366x768 and 100/125/150/200% DPI, mouse-only Save/Cancel and CTRL+UA 45→30 save/readback/LIVE effect (without changing live operator Data during CI).
- Creative Bloq Naruto 3-photo replay (all surviving images must be story-bound), previous #934, gallery positive controls, no unrelated shopping photo.
- Real post comparison on each channel, newest 1,472 operator judgments, local-news short-source policy, dedupe and queue load, cost attribution.
- No automatic Telegram deletion, no replays of UNKNOWN receipts, never force news quota, preserve budgets and operator channel settings.

## Open/known limitations
The queued-job throughput bottleneck, inaccurate short-news rejections, repeated utility-event posts, broken external RSS endpoints, and the full editorial 1,472-label replay remain open until proven by independent LIVE acceptance. This candidate does NOT certify those defects fixed. GitHub CI is not equivalent to Windows operator acceptance. Do not merge or deploy just because code was pushed.

See ProductVault canonical 01_PRODUCT/AUTOPILOT, issues #294-#297.
