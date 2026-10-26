# Autopilot 2.2.36 — verified split Telegram photo/video recovery

**Official Windows Portable release requires PR CI 4/4, Windows native release/Defender verification, and publication of v2.2.36 with SHA256.** Source changes alone are not operator release.

## Fixed
- Telegram text posts may point to distinct photo/video messages via source-authored same-channel media URLs or explicit Telegram replies. The source collector now fetches **up to 3 exact post IDs per channel cycle** when those posts fall outside the visible `t.me/s/` window.
- Reply link handling recognizes `/channel/id`, `https://t.me/channel/id`, `https://t.me/s/channel/id` and exact numeric reply metadata, while refusing other channels and malformed links.
- Only exact matching channel/post ID and media-only entries are imported. A different ID in the embedding HTML, adjacent posts with no positive ownership, multiple conflicting claimants, and unrelated photos remain rejected.
- The source layout now declares `stitch_policy=explicit_reply_group_or_source_link_v236` rather than a misleading adjacency policy marker. Media provenance and prepublish safety checks remain in effect.

## Safety and migration
- No change to operator Data, Google Drive OAuth, telemetry security, source lists (36/18/57), publication intervals (45/30/5 minutes), budgets (OpenRouter $3/day and $20/month), previous COMMITTED deliveries, or UNKNOWN #66297 quarantine. No automatic replay.
- This does **not** auto-attach unverified neighboring Telegram collages. For those, positive source ownership is still required; diagnostic counters will continue to report missing proof.
- After official release, stop 2.2.35, back up original Data, extract into a new folder and import original Data. Validate real LIVE `version=2.2.36`, 3/3 workers/collectors, independent `autopilot-oauth`, and source→published media parity. Keep old directory as rollback.

## Acceptance
- Tests cover exact-source reply parsing, root reply metadata, positive photo URL, positive explicit reply without URL, ambiguous owners, unrelated adjacent images, wrong embedded post ID, foreign channel and bounded number of exact fetches.
- Native Windows compilation and full pytest, installation bootstrap, signing and Microsoft Defender must pass before official GitHub ZIP is distributed.
