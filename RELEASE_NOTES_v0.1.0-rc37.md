# UA FREE Telegram Autopilot v0.1.0-rc37

Stabilization/editorial-quality release based on RC36.

## Editorial changes
- Stricter newsworthiness gate rejects guides, explainers, shopping/accessory roundups, soft conference/column/poetry pieces and obvious multi-topic editorial mashups before AI writing.
- Media remains mandatory. No relevant photo/video means `SKIP_NO_MEDIA`; a Telegram media rejection never degrades into a text-only post.
- New CTRL+UA newsroom writer contract: hook first, 3–6 memorable verified details, variable structure, no forced four-paragraph summaries, no explanatory filler or recap endings.
- Topic-near synthetic few-shot examples teach style without importing facts from another story.
- Final human-interest editor is mandatory and restricted to trusted Codex/Gemini. If it cannot produce a factual, natural and non-formulaic Ukrainian result, the article retries instead of publishing the safe-but-boring draft.

## Stability / efficiency
- Production writing no longer burns time across NVIDIA/Groq/Cloudflare/local fallbacks. Those providers remain available for diagnostics/LAB; unattended production writer/editor routing is Codex -> Gemini.
- Chronic source failures use persistent adaptive backoff: 429/403, wrong content type/feed HTML, network and timeout errors receive progressively longer pauses and recover immediately after a successful check.
- Cache marker bumped to `telegram-post-v22`, so pending cached RC36 drafts are regenerated with the new editorial contract.
- Canonical Windows release no longer uses the custom native launcher that triggered Microsoft Defender on the local RC37 candidate. `UA_FREE_Telegram_Autopilot.exe` is an unchanged official `pythonw.exe` signed by Python Software Foundation; GitHub Actions verifies the Authenticode signer, smoke-tests startup, updates Defender signatures, scans the extracted runtime and scans the final ZIP before publication.

## Compatibility
- No SQLite schema change.
- Existing `Data` can be copied unchanged from RC36.
