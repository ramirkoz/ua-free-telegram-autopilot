# UA FREE Telegram Autopilot v2.1.1 — source access, first test baseline

Status: pre-release, requires operator live QA before promotion.

## Implemented in this build
- Preserves every 2.1.0 official-source, semantic-dedupe, Telegram media, fact guard and editorial QA policy.
- Optional per-source Jina Reader fallback for RSS and web-page article enrichment when a normal native HTML extraction produces less than 250 source characters. Opt-in checkbox in Settings -> Channels -> Sources -> Edit; OFF on all existing sources by default.
- Primary RSS/HTML extraction stays first; never sends Telegram messages to Jina. Jina receives a public URL only for an operator-selected source; it is external processing.
- Strict bounded external response (512 KiB, 15-second maximum request), public HTTP(S) article URL validation; no raw IP targets, local hosts, credentials or nonstandard ports.
- Source URL and native article media are preserved; provenance recorded in article_layout_json and reader usage events. Optional reader failure preserves original RSS summary and content pipeline.
- Maximum 2 optional reader attempts per source collection cycle and 70-second source scheduling guard. No background paid discovery, social scraping or account access.
- Added opt-in, URL-safety, provenance, successful-native-reader and failure fallback regression tests.

## Pending work within the 2.1.1 roadmap
- Optional Exa discovery is not shipped or enabled; requires credential, explicit configuration, source-labelling, cost/limit guard and editorial QA.
- Facebook/Instagram/Reddit/X/LinkedIn adapters are not shipped or auto-enabled; require official access contracts, supported scopes, provenance, authorization and source settings.
- Wider native-reader site corpus and operator validation against slow/403 web sources remain pending.
- The signed auto-update overlay is not verified; use the full Portable and preserve Data until operator acceptance.

Content Tool 2.0.0-rc60 is unchanged.
