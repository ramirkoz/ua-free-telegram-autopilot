# UA FREE Telegram Autopilot v2.0.0-rc36

## Editorial media fail-closed hardening

RC36 closes a publication loophole that could let an unrelated promotional image through even when the semantic/rubbish media validator had rejected every candidate.

### What changed

- Removed the raw first-media fallback from V2 editorial publication selection.
- Editorial channels now publish media only when the existing validator positively selects a relevant image/video.
- If validation fails, the article keeps no media rather than blindly using the first `media_json` URL.
- Existing hard rejects for follow/subscribe/banner/logo/avatar/sponsor/affiliate/promo chrome remain active.
- Added regression coverage for the exact bypass: an opaque first URL is no longer accepted merely because structured metadata is missing.
- Valid media explicitly selected by the validator continues to publish normally.

### Why

The old fallback could bypass all semantic checks when layout metadata was incomplete or probing returned no hero. A CTA image such as a site-follow banner could therefore survive if its URL itself did not contain obvious words like `banner`, `follow`, or `promo`.

### Compatibility

- No database schema change.
- No changes to monitoring-channel album behavior.
- Existing articles, sources, publication history, feedback and credentials are preserved.
- For editorial channels, text-only publication is intentionally preferred over a confident but unrelated visual.
