# UA FREE Telegram Autopilot v2.0.0-rc73 — MANUAL TEST

## Scope

RC73 is a narrow web-media integrity/recovery build for editorial channels. Telegram stitching, monitoring ownership rules, Telegram video recovery/backoff, CTRL+UA policy, and Content Tool are unchanged.

## Changes

- Web media provenance is explicit: `body`, `jsonld_article_image`, `verified_video_poster`, `verified_og`, `rejected_foreign`, `none`.
- Schema.org `Article`/`NewsArticle` images are accepted only when tied to the current article by headline/URL identity, with a conservative single-Article fallback.
- Schema.org `VideoObject` recovery now extracts both the playable video/embed and its `thumbnailUrl`/`thumbnail`/`image` poster. A poster is trusted only when the VideoObject is nested under the matching article or its own metadata matches the story.
- `<video poster=...>` and explicit video-thumbnail metadata are recovered as verified poster candidates. Twitter player cards may use their own `twitter:image` as the player poster.
- Iframe-only video stories are no longer treated as having uploadable Telegram media; a verified article image/poster can therefore satisfy required-media policy while the video link remains attached separately.
- OG/Twitter images fail closed unless the asset itself has story evidence via alt/title tokens, image URL tokens, or matching article ID under verified page metadata. A matching page title alone is not enough.
- Lazy/body image extraction from RC71/72 remains intact (`srcset`, `data-srcset`, `data-lazy-srcset`, `data-original-src`, etc.).

## Safety / deployment

- Manual test only.
- Auto-update remains disabled.
- No canonical Drive/GitHub/Vault promotion.
- No channel IDs or names are hardcoded in production media logic.
