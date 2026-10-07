# UA FREE Telegram Autopilot 2.0.0-rc113

RC113 is the native web-media closure release.

It exists because RC112 source-integrity hotfixes worked, but live telemetry still showed a remaining class of required-media failures on publishers such as FastCompany: the story page visibly had a lead image while the publication pipeline reached `source_media_count=0`.

## Page-level hero recovery
- Reuses the bounded page image candidate set already collected by the article parser.
- Recovers a lead image that is rendered outside semantic `<article>` / `<main>` when the asset has strong article identity evidence.
- Strong evidence is title-token overlap, image-URL overlap, or an explicit hero/lead/featured/story-image wrapper.
- Generic large page images are not accepted merely because they are large.
- Recommendation, sponsor, banner, logo, avatar and other existing hard-noise filters remain active.

## Trust order
Native web-media trust order is now:
1. article/main body media;
2. schema.org Article.image;
3. verified video poster;
4. strongly article-bound page hero;
5. strict OG/Twitter fallback.

This closes the layout class where the browser renders the hero as a sibling of the article body.

## Media diagnostics
Article layout now records:
- `page_image_candidates`;
- `explicit_gallery_signal`;
- `explicit_gallery_candidates`;
- `jsonld_images`;
- `body_media`;
- `selected_provenance`.

This makes the next live failure diagnosable without guessing whether the candidate disappeared at HTML parsing, article binding, validation, or publication.

## Preserved RC112 contracts
- complete gallery handling up to 24 validated source-owned media items;
- source/content identity binding and wrong-source publication block;
- operator media policy semantics;
- YouTube/Vimeo handling;
- source cooldown and QUALITY retry behavior;
- delivery journal and human-approval lifecycle.

## Live acceptance
RC113 is accepted only if:
1. telemetry reports `version=2.0.0-rc113`;
2. FastCompany/TrendHunter-style pages with visible story media no longer systematically hit required-media recovery;
3. page-hero recovery does not leak recommendation/banner/logo artwork;
4. galleries remain complete and ordered;
5. source_url/canonical_source_url/published_source_url remain bound to one article identity;
6. delivery unresolved remains 0;
7. workers/collectors remain healthy;
8. overnight run completes without P0/P1.

Next planned versions:
- RC114: automatic feedback/statistics refresh;
- RC115: full OpenRouter provider;
- then 2.0.0 stable after live acceptance.
