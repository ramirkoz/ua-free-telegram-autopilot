# UA FREE Telegram Autopilot v2.0.0-rc69 — MANUAL TEST

## Telegram media integrity
- Restores bounded Telegram text+adjacent-media ownership: consecutive media-only messages within the existing 5-minute adjacency window are attached to the source text post.
- Restores the short hold for a fresh trailing text-only Telegram post so a following media message can arrive on the next poll.
- A Telegram video poster is now diagnostic metadata only, never a substitute for the original playable video.
- If a source Telegram post declares video but only a poster/no video is available, processing is held with `TELEGRAM_VIDEO_PENDING` until the real video is recovered.
- Exact/direct recovered videos continue to publish normally.

## Commercial/editorial profile
- Adds a visible broad-audience lane to the commercial editorial profile: general-interest/retellability/culture/surprise/consumer relevance can pass even when the story is not a classic marketing case.
- One-time migration appends `[BROAD_AUDIENCE_RC69]` rules to the channel's visible policy fields and adds editable broad-interest thresholds to `editorial_thresholds_json`.
- No production rule uses a channel name or channel ID.

Auto-update promotion remains disabled for this manual test build.
