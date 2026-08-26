# Changelog

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
