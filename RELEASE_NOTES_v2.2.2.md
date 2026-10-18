# Autopilot 2.2.2 — Responsive Media Deduplication Operator Test

**Status:** Windows Portable TEST release. Editorial LIVE acceptance is pending.

## Fix
- CTRL+UA web galleries preserve **all genuinely different images**, with NO one-image limit.
- Final Telegram preparation detects high-confidence duplicates of one illustration across JPEG recompression, responsive resizing, and centered/edge crop variants.
- Preserves video attachments and unrelated photographs.
- Existing SHA-256, perceptual hash, and source validation remain active.

## Validation
- Synthetic regression cases: 3 views of one illustration -> 1; three genuinely different compositions -> all 3; mixed photo/video -> video retained.
- Independently checked **operator-provided screenshots** for the two Tom's Hardware defects (Wi-Fi hologram and F-22): both side images align to the main image as near-identical pixel crops. Screenshots are not uploaded into the public repository.
- **Limitations:** this is screenshot-crop verification, not access to original CDN image bytes nor confirmation in operator LIVE Telegram. After installation, review the next matching source-gallery articles.

## Installation
Stop prior Autopilot; back up the complete `Data` directory, including encrypted settings. Unpack 2.2.2 into a new empty folder. Move the backed-up `Data` into it and test CTRL+UA. Preserve the old 2.2.1 install for rollback. Never upload `Data/secrets.*`.

## Acceptance
For a one-illustration responsive gallery, `visual_duplicates_removed` must increase and `published_media_count` should be 1. For three distinct pictures, `published_media_count` may be 3. Review images in Telegram, not only the transport's `COMPLETE` status.
