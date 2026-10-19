# Autopilot 2.2.3 — Media Evidence Core Operator Test

**Status:** Windows Portable TEST release. Editorial LIVE acceptance is pending.

2.2.2 did **not** fix the F-22 case: a replay of the original Tom's Hardware page and CDN bytes through the 2.2.2 code still published 3 renditions plus a site promo image. 2.2.3 fixes the causes instead of tuning thresholds. All changes are universal mechanisms; channel-specific behaviour stays in channel settings (media policy, commercial profile). No per-site code, no one-image limit.

## Fixes
- **Source level: one asset, many renditions.** New `media.canonical_asset_key` recognises CDN transform segments (`t:0,l:420,cw:1080…`, `w_800,c_fill`), rendition suffixes (`-1920-80`, `-1200x675`, `@2x`, `.jpg.webp`) and opaque upload IDs. schema.org `Article.image` lists of one photo in 16:9/4:3/1:1 are no longer treated as a gallery; distinct uploaded assets still are.
- **Pixel dedupe without a contrast blind spot.** The crop/rendition check ran only when the earlier image had a dHash fingerprint; low-contrast photos (a jet on clear sky) never got one. The new matcher searches scale + offset in both directions and verifies a high-pass detail map at the best alignment, so "same photo, other crop" merges while "same sky, plane moved / mirrored / erased" does not. Pillow only, no new dependency; faster than 2.2.2 on real pages.
- **Honest story evidence.** CSS class names (`widget membership-slider news-page…`) no longer count as proof that an image belongs to the story. A lead body image (position ≤ 0.35) whose asset the page itself declares as the article image (og:image / twitter:image / schema.org) is accepted as story media.
- **Commercial gallery relaxation narrowed.** Empty-alt gallery items keep the RC112 relaxation; cards whose own alt describes a different story ("Top 90 Interactive Trends…") or sit in related/recommended containers do not.
- **Typed media drop reasons.** `publication media gate` and `source page media recovery` events now carry `media_drop_reasons`, e.g. `{"http_403": 11}` instead of an opaque "filtered by media policy". CDN 401/403/429 are reported as access decisions, not bad media.
- **READY media recovery no longer burns its attempts in a minute.** The publisher records which source assets it already tried; re-collecting the same assets (other renditions, other order, the publisher's own recovery rewrite) does not clear the media backoff. `media_recovery` state now survives re-polls.

- **One fresh recovery for items the old loop archived.** One-time startup migration: READY items archived as `MEDIA_REQUIRED_PERMANENT` within the last 48 h (with finished copy) return to READY for one bounded recovery under the 2.2.3 rules; channel TTL still applies.
- **Vector icons are not media.** `.svg`/`.svgz` are never media candidates (menu icons were counted as an 11-item "gallery").
- **Replayable media trace.** `media prepared for telegram upload` events carry `media_trace` (kind, URL, SHA-256 of uploaded bytes, size, kept/removed) for exact incident replay.

## Commercial observability (ПРОДАНО!)
- **Structured selector rejections.** The channel-fit selector returns a `reject_code` (off_topic, weak_audience_hook, routine_pr, weak_mechanism, weak_visual, duplicate, insufficient_facts, stale, other); rejection reasons are stored as `[code] reason`. Telemetry categories use the code first and fall back to the old text matching only for legacy reasons. Selector thresholds are unchanged.
- **24 h report.** `commercial_throughput.channels[].window_24h`: processed, published, rejected, reject categories, value-score buckets of rejections, media-permanent losses, READY items waiting for media.
- **"No publications today" signal.** A channel that processed work but published nothing after its configured starvation window of open publishing time is DEGRADED with a dedicated incident — also after the window has closed for the day (previously it showed HEALTHY in the evening).
- **Blocked sources notice.** Sources returning HTTP 403 three or more times in a row are listed as an INFO operator notice in the UI incident line (no diagnostic bundle, not counted as a runtime problem).
- **Release PR builds Windows assets.** The release workflow now builds and tests the portable on release PRs (`RELEASE_NOTES_v*.md`) without publishing; Drive sync skips PR runs.

## Validation
- New regressions `tests/test_223_media_evidence_core.py` (16 cases) and `tests/test_223_observability.py` (6 cases): asset keys, JSON-LD renditions vs real gallery, low-contrast renditions 3→1, same-sky different frames kept, video never merged, CSS context not evidence, page-declared lead image kept, recommendation cards excluded, 403 reported as `http_403`, re-poll keeps backoff, genuinely new asset unblocks.
- Full suite green locally (Windows, Python 3.12); CI 4/4 on the PR.
- **Replay of original public pages and CDN bytes** through the production functions (`hydrate_article_page` → `prepare_article_media` → `prepare_telegram_media_list` → `remove_visual_duplicates`), 17 articles from Tom's Hardware, Ars Technica, The Decoder, Space.com, The Verge, TechCrunch: F-22 4→1 and Wi-Fi 2→1 (renditions and promo removed); the other 15 articles publish the same images as 2.2.2.
- Pixel matcher on original bytes: 14/14 (7 renditions merged, 7 different frames/images kept).
- Negative corpus: all 406 pairs of the 29 distinct real images from those 17 articles — 0 false merges; plus 45 pairs of synthetic same-scene burst frames — 0 false merges.
- Latency (Windows, one core): real pages p95 124 ms per image pair (most unrelated pairs are rejected by a colour-histogram prefilter in < 1 ms). Adversarial worst case — 10 near-identical frames of one low-contrast scene (45 full comparisons) — about 2.8 s; the 1.5 s target is met for realistic galleries, not for that adversarial case.
- **Limitations:** not yet observed in operator LIVE Telegram. TrendHunter CDN blocks automated requests (HTTP 403, Akamai); 2.2.3 reports this truthfully but does not and will not bypass it — the source needs an operator decision (feed, permission, or replacement). Commercial selector strictness is unchanged.

## Installation
Stop prior Autopilot; back up the complete `Data` directory, including encrypted settings. Unpack 2.2.3 into a new empty folder. Move the backed-up `Data` into it. Preserve the old 2.2.2 install for rollback. Never upload `Data/secrets.*`.

## Acceptance
- CTRL+UA: a single-illustration responsive gallery publishes 1 image; a gallery of genuinely different photos keeps all of them. Review images in Telegram, not only the transport's `COMPLETE` status.
- ПРОДАНО!: every media rejection shows `media_drop_reasons`; no `MEDIA_REQUIRED_PERMANENT` earlier than about 2 hours after the first attempt.
