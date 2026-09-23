# UA FREE Telegram Autopilot v2.0.0-rc71 — MANUAL TEST

Focused web-media integrity repair for commercial editorial channels.

- Commercial-editorial channels receive visible `media_policy=required`; no more text-only publication when media is missing.
- Web article media trust order is now: structural article/body media → schema.org Article/NewsArticle image → verified OG/Twitter fallback.
- Generic OG/Twitter images are rejected when their alt metadata does not overlap the article title; an unrelated page/social image can no longer silently become the post image.
- Added JSON-LD Article.image recovery for JS-heavy publishers and extra lazy-image attributes (`data-srcset`, `data-lazy-srcset`, `data-original-src`, `data-image-src`).
- RSS/feed media is still available to the collector, but a successfully extracted article image takes precedence.
- Publication telemetry now reports `web_media_provenance` (`body`, `jsonld_article_image`, `og_verified`, `og_rejected_unverified`, `none`).
- No channel name or channel ID is hardcoded. The commercial media requirement is seeded from the explicit `commercial_editorial` profile into normal editable channel settings.
- Telegram stitching/video behavior from RC70 is unchanged.
- Manual test build: no auto-update promotion.
