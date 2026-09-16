# UA FREE Telegram Autopilot v2.0.0-rc45

## Editorial single-media publish boundary

RC45 fixes an editorial publication boundary regression that could send every source-page image as a Telegram carousel.

- Restores the existing EDITORIAL invariant: zero or exactly one relevant media item per post.
- Publisher now uses `build_publication_media_bundle(channel, article)` instead of the raw source media bundle.
- CTRL+UA and other editorial channels can no longer emit multi-image carousels from article-page media.
- MONITORING channels continue to preserve genuine source-owned albums.
- Required-media editorial channels still fail closed when no relevant media can be selected.
- Adds regression coverage for the publisher boundary and editorial-vs-monitoring media behavior.
- No database schema change.
