# UA FREE Telegram Autopilot v2.0.0-rc68 — MANUAL TEST

- Adds explicit Telegram video recovery telemetry for every video-marked post: direct_video, exact_post_video, poster_fallback, or no_video.
- Stores the recovery mode in article_layout_json and includes it in the final publication media-gate event, so live evidence can be correlated with article_id.
- Does not change channel selection, dedupe, source lists, publishing cadence, AI routing, or RC67 media fallback behavior.
- No channel names/IDs are hardcoded. Auto-update remains disabled in MANUAL TEST.
