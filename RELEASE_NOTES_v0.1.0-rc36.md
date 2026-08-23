# UA FREE Telegram Autopilot 0.1.0-rc36

## Media-required + human newsroom style

RC36 preserves the RC35 blocked-source compatibility layer and adds the editorial changes requested after live CTRL+UA review.

### Changed

- Publication is media-required: no validated photo/video means `SKIP_NO_MEDIA` before any expensive AI rewrite.
- Text-only Telegram publication is disabled, including the old media-to-text QA fallback.
- Telegram rejection of validated media no longer falls back to a plain text post.
- Featured/OG images with no semantic story metadata are rejected instead of being trusted solely because a publisher marked them as featured.
- The first rewrite prompt explicitly avoids fixed four-paragraph AI-summary structure, obvious explanations, filler transitions and repeated conclusions.
- Every otherwise publishable candidate receives one bounded trusted HUMAN STYLE PASS through Codex/Gemini.
- Humanized text is revalidated for source numbers/years, Fact Guard, Ukrainian language, editorial blockers and copy-edit content preservation.
- If the trusted human-style pass is temporarily unavailable or fails QA, the already-safe pre-humanized candidate is retained rather than turning style polishing into a new availability failure.
- Unpublished cached rewrites move to `telegram-post-v21` so old text-mode candidates cannot bypass the RC36 contract.

### Preserved

- RC35 HTTP 401/403/429 source handling, bounded feed fallback and Reuters rejection remain active.
- RC34 native Windows launcher and packaged-EXE smoke gate remain unchanged.
- Existing `Data`, SQLite schema, AES-GCM secrets, source priorities, dedupe, Fact Guard and Telegram unknown-outcome protections remain compatible.
