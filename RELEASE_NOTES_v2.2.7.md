# UA FREE Telegram Autopilot v2.2.7

## Telegram original media integrity

- Added exact-post photo, collage and grouped-album parity preflight before publication in monitoring channels. Uses the concrete Telegram data-post ownership boundary; never borrows another source message's artwork.
- Restores original source-owned photo and video media when an exact-post embed provides uploadable files. If a photo album is incomplete or only an unresolvable photo/video placeholder exists, returns TELEGRAM_PHOTO_PENDING or TELEGRAM_VIDEO_PENDING and retries safely rather than posting bare text.
- Truly text-only original posts remain publishable with preferred/optional media policy. Previously delivered posts are not automatically resent.
- Adds explicit prepublish telemetry for expected photo/video presence, confirmed source media, candidate counts and recovery/withholding reasons.
- Retains all v2.2.6 fixes and protects original Data, Telegram delivery journal and UNKNOWN delivery quarantine.

## Verification

- Regression cases cover photo collage, album completeness, video with photos and genuine text-only inputs. Windows CI and GitHub-built Portable asset required before operator deployment.
- The reported 09:26 Mykhailivska photo loss was created by v2.2.5 before v2.2.6 startup; exact original post ID remains unknown.
- Operator LIVE acceptance of v2.2.7 is still required for full photo/video parity in actual Telegram publications.
