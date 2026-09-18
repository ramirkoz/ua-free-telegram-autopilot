# UA FREE Telegram Autopilot v2.0.0-rc56

RC56 fixes event-level duplicate misses in CTRL+UA and makes PRODANO video stories video-aware.

- Adds a durable 30-day / 2000-event-per-channel published-event ledger, backfilled from existing PUBLISHED history and checked at the final publication gate.
- Adds high-information scientific-name matching (for example exact binomial taxon names) so independent rewrites of one species discovery are blocked without requiring matching numbers.
- Adds CTRL+UA subject+method scientific fingerprints so the same study is recognized across different reporting angles (for example Herculaneum scrolls + lead ink + X-ray + digital unwrapping).
- Replaces the RC53 every-Latin-word entity extractor with proper-name extraction, preventing generic English marketing vocabulary from becoming fake entities in PRODANO.
- Disables the broad concept+numeric fallback for PRODANO while retaining stronger brand/fact/action duplicate evidence.
- Emits a final prepublish nearest-event trace when an article is allowed through, making future misses diagnosable from telemetry.
- Makes video-story detection use title + article text, not title alone, and expands campaign/video vocabulary.
- Recovers schema.org VideoObject embed/content URLs from JSON-LD when publisher pages render video via JavaScript.
- For PRODANO/editorial stories with YouTube/Vimeo embeds, prefers a video preview when available and always carries the canonical video as a dedicated clickable `🎬 Відео` footer link.
- Emits `VIDEO_EXPECTED_BUT_NOT_FOUND` when a PRODANO story is clearly about a video but extraction found no usable video target.
