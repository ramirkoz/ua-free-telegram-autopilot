# Autopilot 2.2.35 — monitoring split-media evidence and bounded video recovery

**Candidate, not operator-installed**. Base: 2.2.34. Publish only after PR and main CI 4/4, native Windows and Defender SUCCESS, exact signed ZIP and SHA256 asset.

## Actual changes
1. Monitoring only: a read-only and bounded `telegram_media_provenance_60m` record per channel in canonical Drive telemetry separates **verified multi-message source media** from **unverified media-only neighbors**. Includes a maximum of 6 public source/candidate links with article IDs. This is a diagnosis, **not** permission to attach neighboring media. Visible count in the operator Supervisor pane.
2. Telegram exact video recovery: successful exact-post proof of "no video yet" gets a 10-minute process-local negative cache (bounded to 512 posts). Timed-out/HTTP failed requests are **never** cached. Direct videos and newly available video files remain eligible on later polling; no unrelated source media is borrowed.
3. Regressions on deduplicating unresolved observations, sample bounds, verified vs unverified provenance, temporary exact video absence, TTL expiry, and retry of network failures.

## Explicitly not changed
- Operator Data, source lists 36 / 18 / 57, source cadence, publishing intervals 45 / 30 / 5 min, daily/monthly OpenRouter $3/$20 limits, existing receipts or UNKNOWN #66297, independent Autopilot OAuth and Content Tool.
- No replays or deletions. No automatic attachment of standalone media based on adjacency/time. The operator example from Благовіщенська громада still requires an independently proven source ownership edge for safe *automatic* reconstruction.
- Existing source gate `EDITORIAL_MIN_TWO_SENTENCES` remains intentionally conservative. Thin, ambiguous posts are not expanded with invented facts merely to increase publication totals.

## Acceptance
- All CI and official Windows/Defender release gates passing; verify hashes.
- Copy original Data in a separate-folder Windows install with process stopped, retain old folder as rollback.
- LIVE current_version, worker/collector 3/3, Autopilot OAuth health, channel publication, Drive writes and new `telegram_media_provenance_60m` counters checked. Don't claim a specific split-media fix without a source/post-level positive example.
