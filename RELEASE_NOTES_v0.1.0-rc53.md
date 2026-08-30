# UA FREE Telegram Autopilot v0.1.0-rc53

RC53 is a production-hardening release built from the live RC52 audit. It keeps the working collector, mandatory-media publishing, Evidence Pack / Fact Guard and RC52 split topic/style model, but closes the failure modes observed in real operation.

## Telegram reaction learning

- Reaction learning now uses **only reactions chosen by the connected operator account**, not aggregate audience reaction counts.
- Telegram Premium multi-reaction labels are preserved independently: `👍+🔥` means good topic + good writing; `👎+🔥` means suppress similar topics while keeping the published copy as a positive style example.
- `👍/👎` remain topic-only; `🔥` remains style-only.
- Missing MTProto user-session is no longer treated as silent neutral operation. UI shows a blocking red health state explaining that learning is not working.
- Telegram Analytics authorization immediately bootstraps a reaction refresh for the selected channel.
- Runtime metadata now declares Telethon as a package dependency.

## Freshness and duplicate control

- Page enrichment now extracts publication time from `article:published_time`, common publication-date metadata, JSON-LD `datePublished`, `<time>` metadata and full dates embedded in URLs.
- Publication freshness is **fail-closed**: candidates without a verifiable publication date do not enter automatic publication.
- URL canonicalization now strips `itm_*` plus common marketing/click tracking parameters in addition to `utm_*`, `fbclid` and `gclid`.
- Query ordering is canonicalized, existing Data URLs are re-normalized on startup, and pending canonical duplicates are collapsed before expensive AI work.
- New collection rejects already-known canonical URLs across sources in the same channel.

## Editorial hardening

- CTRL+UA receives deterministic hard vetoes for known off-profile classes observed in the live audit, including entertainment/sports/editorial-policy noise.
- ПРОДАНО! receives a deterministic hard veto for pure personnel/leadership appointment stories.
- The known live regressions around Tim Curry/off-profile material and marketing personnel news are covered by tests.

## AI routing and language QA

- RC53 repairs the stale RC49 prompt-marker routing bug introduced when RC51 changed the newsroom prompt openings.
- Quality-critical RU editor and final UA writer tasks are routed to trusted Codex/Gemini paths again.
- The historically near-zero-yield Groq/NVIDIA/Cloudflare/local fallback path is disabled for final newsroom writing instead of burning cycles after a trusted-writer failure.
- Final semantic QA rejects observed corruption classes including `плей-оф ного` and the `epoxy/epoxies → діоксид` mistranslation.
- Those corruption patterns can no longer receive a misleading 100/100 quality score.
- Cache marker advances to `telegram-post-v34` so unfinished RC52 text is regenerated under RC53 semantics.

## Operational performance

- Repeated LanguageTool degraded/startup audit and UI messages are throttled to a ten-minute interval.
- Audit history reads are capped and old audit rows remain limited to a seven-day operational window.
- Additional SQLite indexes and `PRAGMA optimize` reduce History/dedupe work on larger Data folders.

## Compatibility

- No destructive SQLite reset.
- Existing channels, sources, Bot Tokens, API credentials, publication history and RC52 reaction tables remain compatible.
- Install RC53 into a fresh program folder and copy the complete existing `Data` directory from RC52. Do not overlay runtime files.
