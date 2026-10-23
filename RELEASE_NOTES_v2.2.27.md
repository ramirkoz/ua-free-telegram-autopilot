# Autopilot v2.2.27 — source-fact briefing, exact Telegram media repair, queue pressure

## Shipped code changes

1. **Reader-first source fact card in LIVE editorial path.** `v2/source_fact_card.py` deterministically builds an immutable, bounded briefing from exact original source excerpts with title and source identity. It pins the original lead, complete sentences that contain percentages/money, attribution and actionable date/address terms. It labels snippets as verbatim source facts, never interprets numbers or invents actor relationships. Both the actual writer and trusted final editor receive the same source-owned fact card; ANGLE and learned style do not enter it. No additional AI request, no new payment or provider.
2. **Publication-level exact Telegram gallery repair.** Previously an article containing seven verified photos of one exact post plus seventeen neighboring items was left blocked indefinitely with `MEDIA_CROSS_POST_CONTAMINATION`, even when exact source media was obtainable. On *positively confirmed exact-post preflight* (outcome `confirmed` / `video_recovered` only), the publisher may replace its contaminated gallery with ONLY the matching exact post's verified media. It removes unrelated media blocks, recalculates the actual publication bundle, checks strict equality and photo/video shortfall, then persists the repair. If parity cannot be proven, prior fail-closed block remains. No cross-post attachment, no degraded no-media publication, no silent unknown-delivery resend.
3. **Readable capacity diagnosis:** `capacity_window` now reports selection jobs per optimistic publishing slot, pressure band and that pending selection tasks ARE NOT obligated posts. Existing overloaded `FRESHNESS_FIRST` logic remains; this does **not** secretly change the user-defined 45/30/5-minute cadence, backfill or auto-remove queued items.
4. Added regression tests `tests/test_2227_source_fact_card_and_media.py` for original-source statistics, text provenance, incomplete/truncated source, capacity limits, safe exact source gallery repair and network-uncertain no repair.
5. Version metadata updated consistently in all package files to `2.2.27`.

## Safety and scope

- Operator `Data`, 36/26/57 source sets, three channel policies, UI settings, $3/day/$20/month AI spending caps, model cascade, COMMITTED delivery ledger, archived receipt SHA and quarantined UNKNOWN #66297 remain untouched. No remote commands, no auto replay.
- `v2.2.26` remains last known operator LIVE version until separate installation is verified. No automatic Windows update claimed.
- Source fact cards are deterministic grounding hints and preserve exact quotes; **they do not prove semantic entailment or guaranteed human-readable prose**. Actual 2.2.27 posts in all 3 channels require side-by-side original source audit, especially `ПРОДАНО!` / Fast Company #76521 pattern.
- The backlog is due selection work, not a number of guaranteed publishable stories. This release improves transparent pressure diagnostics, not magically removing 110 jobs or shortening operator intervals. HTTP403 Rest of World/Springwise remains external source access requiring official feed/permission/substitution; provider quota/429 are not bypassed.
- Exact Telegram media repair is narrow and guarded. No foreign media source, no owner guessing. If source media cannot be positively confirmed, existing retry/quarantine behavior remains.

## Release and acceptance gates

- PR CI 4/4 Ubuntu & Windows Python 3.11/3.12/3.13, native Windows ZIP/Defender, signed GUI/credential migration; do not merge on failures.
- Official main GitHub Actions native Windows Release + main CI must pass, and v2.2.27 tag/Portable ZIP hash/size verified, prior to shipping.
- Manual operator safe separate-folder Windows installation with preserved original V2 Data and no overlap, then LIVE telemetry and editorial/media QA. Keep 2.2.26 manual rollback.
