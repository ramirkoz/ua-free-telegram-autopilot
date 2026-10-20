# UA FREE Telegram Autopilot v2.2.8

## P0 hotfix: article-bound web pictures

- Fix the observed 2026-10-20 CTRL+UA wrong-image post: The Register article #67109, source story ID 5303961, unrelated cosmetics thumbnail `image.theregister.com/5303967.webp`; the prior 2.2.7 editorial pipeline accepted it as `body` media and then correctly reported transport as COMPLETE. Transport integrity alone is not editorial media relevance.
- Track the link destination of in-page web image cards from HTML extraction through stored article layout to publication. Reject candidate thumbnails that link to a different story even when captions, dimensions or schema hints falsely appear plausible.
- Add a separate cross-story asset guard for The Register's numerical article-image IDs. Image asset #5303967 can never be attached to story #5303961 on merely sharing the publisher's CDN.
- New drop reason telemetry: `linked_other_article` / `cross_article_image_id`. Keep the required-media gate intact: if there is no verified image, defer publication rather than fabricating artwork. Do not relax this gate or auto-replay the already sent bad message.
- Preserve valid article-bound stills, source galleries, explicit image zoom links, and all v2.2.7 exact-post Telegram photo, album and video parity guards. Monitoring Telegram original media is not subject to the web-image filter.

## Regression and release acceptance

- New regression `tests/test_228_web_media_story_binding.py` checks link attribution in extractor, unrelated linked story previews, the exact 5303961/5303967 negative reproduction even with schema flags, a positive matching image, zoom links, other publishers' verified images, and true text-only stories.
- All existing regression/Windows CI and actual Windows Portable artifact must pass before release is labeled ready. GitHub CI success is not operator LIVE editorial acceptance; operator must install the new Portable version, observe real posts and confirm lack of unrelated images.
- Operator prior LIVE v2.2.7 observed separate DNS failures on 2026-10-20. This patch does not change source-network policy or interfere with the published Telegram delivery journal / UNKNOWN quarantine.
