# UA FREE Telegram Autopilot v0.1.0-rc60

RC60 is a universal editorial-quality hardening release. It does not add channel-name routing or channel-specific business logic.

## Cross-source event dedupe
- Strengthens duplicate detection for the same event reported by different outlets with different wording.
- Adds a high-precision cross-source title fingerprint using named entities, event family, shared facts/numbers and title overlap.
- Covers both the cheap pre-writer duplicate gate and the final pre-Telegram semantic duplicate gate.
- Regression cases include the duplicate ChatGPT/DSA event and the duplicate Chipotle 100-creators campaign observed in live output.
- Same-brand but different events remain separate.

## Natural Ukrainian language QA
- Adds a channel-agnostic language rule: published Ukrainian must not become a mix of Ukrainian grammar and untranslated professional English jargon.
- The writer is instructed to translate ordinary professional vocabulary while preserving brands, product/model names, standards, acronyms and terms that genuinely lack a stable Ukrainian equivalent.
- Detects common escaped jargon such as `social-first`, `hot takes`, `qualified views`, `run rate`, `shot list`, `creator payouts`, `fan funding`, `ad revenue`, `self-serve`, `open source` and `fair use` when left unexplained in Ukrainian prose.
- If jargon still escapes the writer, RC60 runs one fact-preserving language-only repair against the original Evidence Pack. If a safe repair cannot be produced, publication fails closed instead of sending mixed-language copy.

## Universal architecture preserved
- Channel topic, audience, selection rules, rejection rules, style, examples and extra prompts still come only from per-channel `ChannelPolicy` settings.
- RC60 contains no special routing for CTRL+UA, ПРОДАНО! or any future channel name.
- Source priority remains a per-source setting (1–100) and continues to control which fresh stories get processed first.

## Cache
- Publication format marker advances to `telegram-post-v37` so pending cached rewrites are regenerated under the new language rules.

Install into a fresh folder and copy the complete existing `Data` directory from RC59.
