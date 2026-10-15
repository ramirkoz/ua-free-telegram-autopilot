# Autopilot v2.1.15

- Telegram municipal monitoring: reliably combine adjacent split text and photo albums when the source publishes them as separate consecutive Telegram messages.
- Preserve entire preceding album even when the following text message includes its own photo; include following media-only entries where applicable.
- Retain existing five-minute adjacency policy and existing text-first album behavior; do not introduce timestamp-only blocking.
- Regression tests cover text before album, album before text with own photo, album/text/additional media, and nonconsecutive boundaries.
- Upgrade using separate Windows Portable folder. Migrate Data from v2.1.14; retain original folder for rollback. No autonomous source credentials migration outside Data.
