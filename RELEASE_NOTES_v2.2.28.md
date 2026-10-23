# Autopilot 2.2.28 — focused source-fact rewrite + OpenRouter route compatibility

## What this release changes

1. **2.2.27 factual QA loop repair.** The live monitoring article #77337 kept being selected anew and sent back to writer/final editor, then failed source polarity/uncertainty at the final publication gate. Now the process checks whether the article has a previous PREPUBLISH_SOURCE_SAFETY/PREPUBLISH_QA error with an intact draft and bounded retry history. It first asks the **trusted final editor** for one targeted repair from ORIGINAL SOURCE, with explicit source polarity/uncertainty/casualty instructions. It does **not** rerun selection or repeat full writing when this one pass satisfies all immutable source and editorial gates. If repair does not pass, it remains blocked by the same factual QA and can fall back to existing bounded full writer flow. No publication of a failed fact.
2. **Accurate factual exhaustion codes.** Retain legacy `rewrite_oversize` durable retry queue for compatibility but record `SOURCE_FACT_QA_BLOCKED` or `PREPUBLISH_QA_BLOCKED` at the terminal attempt instead of incorrectly labeling unsupported factual content as `TELEGRAM_OVERSIZE_BLOCKED`. The 3-attempt safe bound is preserved; no reset of existing Data/retry history and no replays.
3. **Task-incompatible AI endpoint isolation.** OpenRouter `scaledown/summarize` rejects the `response_format` used for JSON editorial selectors; `scaledown/extract` requires a custom entity schema. Both are filtered from automatic catalog AND manually configured general-chat candidates for all ordinary Autopilot tasks, including health checks. Other user-selected models and route order remain unchanged; no paid pilot, no model auto-enablement. Provider quota/Cloudflare/Ollama timeouts keep existing backoff.
4. New regression suite `tests/test_2228_focused_source_repair.py`: targeted correction avoids rerunning selector, validates both hard and soft gates, fails closed on bad correction, persists source-specific terminal QA, filters incompatible OpenRouter IDs and keeps normal chat models.
5. Package version bumped to 2.2.28 in `VERSION.txt`, `V2_VERSION.txt`, `PUBLIC_VERSION.txt`, Python package versions and `pyproject.toml`.

## Explicit boundaries and unresolved LIVE problems

- This is an evidence-led repair of wasted factual retry cycles, NOT a claim of universal semantic entailment or that all three channels' rewrites are already editorially accepted. Source + model outputs need post-installation review against actual articles.
- **ПРОДАНО!** still has low publication yield: in operator 2.2.27 snapshot, 119 of 132 commercial selection jobs were rejected in 24h; the major categories include weak broad interest, routine B2B PR and low creative/visible mechanism. This release does not silently relax user editorial policy to inflate output. The actual source-to-post and rejected-high-score audit remain the next operator-backed tuning step.
- **Article #77342** is still blocked due to no verified original video in source-page recovery. We keep fail-closed MEDIA_REQUIRED and existing bounded retries; cannot invent or substitute someone else's video. We do not claim video discovery is fixed without evidence.
- CTRL+UA 101 selection jobs due vs a 45-minute min publish interval, with two legitimate READY slots; backlog cannot all be treated as publishable news. Existing freshness-first priority and aging remain unchanged; no operator schedule edits or global queue reset.
- HTTP403 Rest of World/Springwise, slow Shots/Ad Age, provider 429 and no-final-response models are separate observed external issues. We don't bypass access restrictions.
- Preserve full operator `Data`/SQLite, channel source lists and editorial rules, AI configured budgets $3/day and $20/month, source media provenance rules, media required, 45/30/5-minute intervals, COMMITTED receipt archive and `UNKNOWN #66297` quarantine. No auto-replay, remote commands or local laptop developer testing.

## Release gates

- Feature PR CI Ubuntu/Windows Python 3.11/3.12/3.13 = 4/4; Windows preview Native Release, signed GUI/credential migration/Defender.
- Only then squash merge; require official main CI and native Windows Release PASS, tagged v2.2.28 ZIP and checksum.
- Operator v2.2.27 remains latest installed until a fresh Drive CURRENT proves manual safe separate-folder v2.2.28 import and real cross-channel editorial acceptance.
