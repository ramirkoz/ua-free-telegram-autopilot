# Changelog

## 0.1.0-rc50 — 2026-08-28

### Fixed
- LanguageTool Windows health checks now allow real JVM response time instead of falsely declaring a healthy local server dead after 0.2-0.35 seconds.
- Marketing-channel media extraction no longer discards legitimate campaign creatives merely because metadata contains advertising/marketing/promo vocabulary.
- Channel-aware media filtering keeps sponsor/affiliate/banner/tracker/logo/avatar rejection strict while allowing topical advertising creatives for marketing channels.
- Media is mandatory for every Telegram channel. Missing or Telegram-rejected media never falls back to a text-only publication.
- Added media-stage audit counters so a no-media rejection records raw candidate count and prepared result count.

### Preserved
- RC49 simplified human-readable editorial pipeline and Editorial Learning Loop.
- Existing Data, channels, sources, Telegram credentials, publication history and editorial memory remain compatible.

## 0.1.0-rc45 — 2026-08-27

### Added
- Per-channel **content direction**: `English → Ukrainian` or `Ukrainian / Russian → English`.
- Dedicated native-English newsroom rewrite pipeline for Ukrainian/Russian sources with trusted final editing, number/year checks and cross-language Fact Guard.
- Additive `channels.content_direction` SQLite column; existing channels default safely to `en_to_uk`.
- Pre-rewrite source-event dedupe using title terms, named/product anchors, numbers and source facts before stylistically different rewrites can hide the duplicate.
- Regression case for the cross-outlet Gemini 3.5 Transcribe duplicate observed in the live CTRL+UA feed.
- Multilingual Evidence Pack attribution/high-risk scoring for English, Ukrainian and Russian sources.
- Semantic-profile review for guide/explainer/review/conference-looking titles instead of trusting a cheap literal category match.

### Changed
- Category classifier accepts common JSON/label wrappers and may explicitly return `__OTHER__` when a source is outside the channel profile/categories.
- With configured weights, `__OTHER__` is rejected and a classifier provider outage is retried; editorial balance is no longer silently disabled through `balance skipped`.
- Ukrainian writing instructions now prioritize one dominant idea, usually 2–3 short paragraphs and fewer secondary details.
- Repetitive AI-newsroom scaffolding such as «найцікавіше тут», «але є нюанс», «іронія в тому» and forced closing kickers is explicitly discouraged as a feed-wide template.
- Direction is part of cache marker `telegram-post-v28:{direction}` so changing channel output language invalidates old cached rewrites.
- English output uses `Source` and `Video` UI/footer wording while preserving the existing Telegram/media path.

### Preserved
- RC44 guarded direct-feed source transport.
- RC43 screen-aware channel editor and `Ctrl+S` save fallback.
- RC42 manual per-channel editorial profiles and weights.
- Existing Data, sources, publication history, weights and Telegram credentials.

## 0.1.0-rc42 — 2026-08-26

### Changed
- Replaced RC41's global CTRL+UA topic caps with operator-defined **per-channel editorial weights**.
- Added a per-channel editable editorial profile and manual category-name/weight editor.
- Empty weight list means no topic-balance gate; weight 0 disables that category for that channel.
- Added local-first, AI-fallback semantic classification into operator-defined category names and persisted each article category in SQLite.
- Rolling balance now uses only categories published by the same channel.
- Removed tech-only global topic percentages and reduced the old domain-specific newsworthiness filters to a small channel-agnostic junk filter.
- Added additive SQLite columns `channels.editorial_weights_json` and `articles.editorial_category`; existing Data remains compatible.
- Cache marker advanced to `telegram-post-v27`.

### Multi-channel
- CTRL+UA and a future Marketing channel can have completely different category names and weights.
- No channel inherits `cyber`, `AI`, `space`, or any other topic percentage unless the operator creates that category for that channel.

## 0.1.0-rc41 — 2026-08-26

### Changed
- Replaced the broad RC38 topic buckets with a finer CTRL+UA editorial mix: AI/models/agents, practical open-source tools, robotics/mobility, science/health, space, hardware/compute, consumer tech, tech business/platforms and cyber.
- Removed the blanket topic-balance bypass for ordinary CVEs/critical vulnerabilities that allowed security feeds to dominate live output.
- Added category-specific rolling caps; cyber is limited most aggressively while AI keeps more room as a core CTRL+UA topic.
- RC37 newsworthiness can now rescue genuinely useful non-shopping open-source tools/resources from guide/explainer rejection.
- Shopping/deal/accessory content stays rejected.
- Cache marker advanced to `telegram-post-v26`.

### Preserved
- RC40 factual/language hard gates and soft editorial repair.
- RC38 event dedupe, RC37 source backoff and media-required semantics.
- Existing SQLite/Data compatibility.

## 0.1.0-rc40 — 2026-08-26

### Fixed
- Split hard factual/language safety from soft editorial-quality scoring after RC39 live operation produced zero publish-ready posts.
- Added one targeted repair for safe-but-imperfect UA copy; failed repair keeps the safe original.
- RU bridge length is no longer a publication blocker and bridge provider outage can fall back to SOURCE-only final writing.
- Codex/Gemini remain preferred final writers; Groq/NVIDIA are hard-validated fallbacks.
- Publication-year, formatting-number and generic Latin-token false positives were corrected.
- Added RC40 article/stage telemetry and advanced the cache marker to `telegram-post-v25`.

## 0.1.0-rc39 — 2026-08-26

### Changed
- Replaced RC38 direct Ukrainian generation + mandatory same-style edit with a two-language newsroom bridge: SOURCE → Russian editorial draft → fresh Ukrainian author → SOURCE Fact Guard.
- Removed the 55–80 word / 3–5 sentence / 2–3 paragraph template that made live RC38 output mechanically uniform.
- Restored fuller media-caption copy: normally about 650–890 characters when the story supports it, while keeping the existing 900-character safety budget.
- The internal Russian draft is not evidence and cannot override SOURCE; numbers and years are checked before it reaches the Ukrainian author.
- Added an anti-slop gate for stacked canned transitions and suspicious paragraph symmetry without imposing a fixed replacement structure.
- RU bridge prefers configured non-Codex/free providers or local AI first; final Ukrainian publication remains Codex/Gemini with full factual validation.
- Cache marker advanced to `telegram-post-v24`.

### Preserved
- RC38 event-level dedupe and topic balance.
- RC37 newsworthiness, media-required behavior, semantic media validation and adaptive source backoff.
- Existing SQLite/Data compatibility.

## 0.1.0-rc38 — 2026-08-25

### Changed
- Added stronger cross-source event dedupe for differently worded reports about the same event.
- Added rolling topic balance with a stricter cap for space stories.
- Added a compact 55–80 word editorial contract. This experiment reduced length but was retired in RC39 after live output remained mechanically structured.
- Cache marker advanced to `telegram-post-v23`.

## 0.1.0-rc10 — 2026-08-18

### Added
- Deterministic Evidence Pack selection for long source material so important facts near the end of an article are not lost by blind prefix truncation.
- Deterministic Fact Guard for unsupported Latin product/entity names and strengthened high-risk claims such as first/largest/fastest/record.
- Persistent source-health counters and durable audit trail stored in the existing SQLite database without destructive migration.
- Source-health columns in the UI and a persistent audit-log view.
- RC10 regression tests for Evidence Pack coverage, Fact Guard behavior, health counters, audit redaction and new format-marker compatibility.

### Changed
- Rewrite prompts now consume a bounded Evidence Pack and explicitly preserve uncertainty and attribution.
- Pending RC9 generated candidates are revalidated under format marker `telegram-post-v5` before publication.
- Source collection records successful yield/error health data while preserving existing source polling behavior.

### Preserved production behavior
- New materials still have priority over retries.
- Retry backoff, attempt limits and overall cycle deadlines are unchanged.
- Telegram 900-character media mode and 4096-character text-only mode are unchanged.
- If a photo is rejected by Telegram, the same validated text is sent without that photo.
- Unknown Telegram write outcomes are not blindly retried.
- The existing AI Router order, production Codex skip and installed-Ollama fallback behavior are unchanged.
- Existing RC8/RC9 `Data` and AES-GCM secret format remain compatible.

### Release status
- Local RC10 regression gate: PASS.
- Operator live smoke on the working Windows/Data environment: PASS on 2026-08-18; no regression was reported before repository synchronization.
- Repository synchronization is authorized; GitHub CI must pass before merge to `main`.

## 0.1.0-rc9 — 2026-08-17

### Added
- Bounded multi-provider AI Router adapted from the stable UA FREE Content Tool v1.2.2 architecture.
- Installed Ollama discovery/start and generation-model selection as the final local fallback, with manual loopback llama.cpp fallback retained.
- Separate editorial-decision and Ukrainian-rewrite AI tasks with per-task budgets and deadlines.
- Ukrainian terminology QA for production-observed calques.
- Conservative media-caption validation against source caption/alt metadata.
- Scored Media Engine that prioritizes article-body editorial media and rejects advertising, Cocoon/AI-summary, banners, logos, avatars and tracking assets.
- Telegram upload of a validated hero image as bytes, avoiding publisher CDN hotlink failures.
- RC9 regression suite for `Data` preservation, terminology, captions, media rejection/scoring and AI prompt bounds.

### Compatibility
- Existing RC8 `Data` is preserved.
- Database schema/initialization code is compatible with the RC8 format.
- Secret-file AES-GCM format is preserved.
- No destructive migration or data reset is introduced.

### Release status
- Local source gate: PASS.
- Native Windows live acceptance on the user's real `Data`: PENDING.
- RC9 must not be merged to stable `main` before that live gate passes.

## 0.1.0-rc37
- Tightened CTRL+UA newsworthiness filtering for explainers/guides/roundups/soft editorial content.
- Replaced generic humanization with hook-first newsroom writing, topic-near few-shot examples and a mandatory trusted human-interest final edit.
