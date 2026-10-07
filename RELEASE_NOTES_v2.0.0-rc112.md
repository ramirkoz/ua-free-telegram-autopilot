# UA FREE Telegram Autopilot 2.0.0-rc112

Final stabilization candidate before 2.0 stable.

RC112 combines the planned stabilization pass with two production issues exposed by RC111 live telemetry and operator review:
1. web editorial media reconstruction was still collapsing galleries to a single or zero item;
2. RC111 no-add cooldown was too aggressive for healthy quiet sources, especially Telegram monitoring.

## Full editorial media reconstruction
- Removed the historical EDITORIAL single-media publication invariant.
- One validated source media item publishes as one captioned photo or video.
- Two or more validated source media items remain a Telegram media group/album.
- More than ten media items continue through the existing safe multi-chunk publication path.
- Up to 24 validated source-owned items are preserved.

## Gallery/carousel extraction
- Detects article-owned gallery/carousel/slideshow/slider/swiper/lightbox structures even when they are siblings of the semantic article element.
- Preserves gallery order through article layout and publication.
- Keeps all valid gallery images after existing banner/logo/avatar/ad safety filtering and binary validation.
- schema.org Article.image arrays are recovered as a complete ordered set instead of taking only the first image.
- Gallery ownership is retained in article layout for diagnostics and publication telemetry.

## Embedded video / YouTube / Vimeo
- Article-owned YouTube/Vimeo iframe/embed URLs are preserved.
- YouTube embeds receive a safe preview image when available.
- The canonical watch URL is attached to Telegram as a dedicated video attribution link.
- Direct source-owned video files continue to be handled as Telegram video media.
- Embedded players are represented by their preview plus canonical watch link.
- Mixed photo/video source sets remain supported by the existing Telegram media-group path.

## Commercial/editorial safety balance
- Explicit source-owned gallery media is trusted after hard safety and binary checks even when alt/context metadata is weak.
- Commercial editorial still rejects logos, avatars, trackers, recommendation chrome, affiliate/sponsor banners and other non-content visuals.
- A campaign visual is not rejected merely because its content is advertising/creative work; in commercial editorial that visual is the story.

## Media telemetry
Publication media events now expose:
- gallery_detected
- gallery_items_found
- gallery_items_kept
- video_embed_count
- web_media_source
- video_link on completed media publication

## Source cooldown correction
- RC111 carried EMPTY cooldowns are cleared once at RC112 startup.
- Fast Telegram sources are never cooled merely because several polls contain no new posts.
- Fast web/page sources wait for six consecutive no-add cycles before a short bounded cooldown.
- >=30s zero-add web sources remain SLOW_EMPTY and are cooled because they materially consume collector time.
- >=120s slow-source handling, 403/429/timeout/network cooldowns remain intact.
- Source-health telemetry now reports empty_streak_6plus rather than the over-sensitive 3-cycle threshold.

## Preserved contracts
- RC111 QUALITY local repair, fail-fast and bounded retry remain unchanged.
- RC110 human-approved priority, source-failure health and ghost-backlog reconciliation remain unchanged.
- RC109 cost-aware AI routing/provider discovery remain unchanged.
- RC108 media remains globally non-blocking: if validated media is unavailable, publish text.
- RC107 editorial ownership/dedupe and RC105 delivery journal remain unchanged.

## Live acceptance focus
1. telemetry reports version=2.0.0-rc112;
2. ПРОДАНО! web stories with visible hero/gallery media publish with media rather than systematic NO_MEDIA;
3. gallery stories publish all validated source gallery items in order;
4. YouTube/Vimeo embeds produce a preview where available plus the canonical video link;
5. no unrelated recommendation/banner media leaks into publication;
6. Telegram/community sources no longer show mass EMPTY cooldown merely because no new posts appeared;
7. collector duration remains materially below the pre-RC111 baseline without cooling every healthy source;
8. QUALITY retry efficiency, delivery unresolved=0, human approvals and text fallback show no regression;
9. overnight acceptance completes without P0/P1 incidents before promotion to 2.0.0 stable.
