# UA FREE Telegram Autopilot v2.0.0-rc70 — MANUAL TEST

Narrow Telegram adjacency repair. No channel-specific production hardcoding.

- Fixes the live Vasylivska community failure where video-only post 9852 preceded text post 9853 but RC69 published 9853 as naked text.
- Confirmed Telegram video placeholders now participate in adjacency stitching even when Telegram exposes no downloadable MP4 and the poster is deliberately excluded from publishable media.
- `media -> text` and `text -> media` both preserve consecutive message IDs within the existing <=300 second ownership window.
- A stitched placeholder never publishes its poster. The combined article carries `video_attachment_seen` / `poster_fallback` metadata and is deferred as `TELEGRAM_VIDEO_PENDING` until a real video is recovered.
- Adds `telegram adjacent stitch` telemetry with direction and pending-video evidence.
- Existing RC69 broad-audience PRODANO settings and all other channel settings are unchanged.
- Manual-test build: auto-update remains disabled.
