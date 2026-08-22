# UA FREE Telegram Autopilot 0.1.0-rc35

## Source HTTP 401/403/429 hotfix

RC35 fixes source onboarding and collection for public publishers whose CDN rejects a plain automated request even though the page or a public RSS/Atom feed is available.

### Fixed

- HTTP 401 is now treated like HTTP 403/429 for browser-style retry instead of immediately killing source detection.
- Retry requests add normal document-navigation headers while remaining scoped only to public editorial source fetching.
- Source detection now tries conservative RSS/Atom fallbacks after access blocks.
- Reuters Technology gets explicit public feed aliases before the blocked section page is probed.
- Generic feed discovery now checks section-level and site-level `/feed`, `/rss`, `/rss.xml`, `/feed.xml`, `/atom.xml` and `/index.xml` candidates.
- If a public page blocks the one-time detection probe and no feed is immediately found, the Add Source dialog no longer refuses to save it; runtime collection can still retry/fallback later.
- Runtime page collection now also invokes feed fallback for HTTP 401, not only 403/429.
- Added regression tests covering the exact Reuters Technology HTTP 401 failure reported from the Windows UI.

### Preserved

All RC34 functionality remains intact: native Windows launcher and smoke-test gate, RC33 CTRL+UA editorial policy, source priority 1-100, event dedupe, media-first Telegram formatting, source database migration and AI routing behavior.
