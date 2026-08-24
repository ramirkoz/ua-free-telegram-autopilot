# Changelog

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
- Restricted unattended production AI routing to Codex/Gemini; kept other providers for diagnostics/LAB.
- Added persistent adaptive source backoff for chronic 429/403/feed-content/network failures.
- Preserved RC36 media-required and semantic media safeguards.
