# Autopilot 2.2.39 — LIVE publication crash and deterministic QA efficiency

## Production fixes
1. **P0 LIVE article #83163 (ГРОМАДИ)**: a real `sqlite3.Row` returned by `V2Store.get_article` has no `.get()`. Telegram exact-post parity enforcement tried `article.get("article_layout_json")` when the message had 2 prepared media and the source confirmed only 1. The resulting exception deferred publication, before Telegram transmission. It now uses `article["article_layout_json"]`, valid for both `sqlite3.Row` and `dict`. Positive reply/source-link ownership checks, separate-media proof and anti-contamination blocks are unchanged.
2. **AI repeated-word loop**: the exact hard QA error `Жорсткий QA: сусіднє слово повторено двічі` observed across 8+ paid/free models becomes a stable deterministic `repeated_word` signature. The existing 2-matching-rejections-per-task fail-fast then stops throwing more money at the same defect, without skipping the job-level retry/quality guards.
3. A single lowercase, ≥4-letter directly repeated adjacent word may be *proposed* for removal without inventing any facts, altering quotes, URLs or numbers. The corrected candidate only succeeds when the **unchanged full original source/factuality/polarity/readability validator** approves it. Any uncertain or repeated error is rejected as before.

## Safety gates
- Regression with a real in-memory SQLite `sqlite3.Row` matches the LIVE media scenario, proves confirmed same-source linked media can pass without exceptions, and unlinked neighboring media is still **blocked**. Tests also cover duplicate-word QA and original source-guard integrity.
- No new permission to attach unverified media, publish shadow-only duplicates or alter source truth/polarity. No live article replay and **do not automatically replay historical UNKNOWN #66297**. A deferred READY article follows normal original delivery journal checks before retrying.
- Existing original Data schema, Telegram channel settings and sources (36/18/57), minimum intervals (45/30/5 minutes), OpenRouter budget ($3/day, $20/month), Google Drive independent `autopilot-oauth`, credentials, receipt ledger and media source ownership remain unchanged.

## Release acceptance
- Gate: PR CI Ubuntu + Windows (Python 3.11, 3.12, 3.13) all passing; Windows native release self-test, migration and Microsoft Defender; main CI/release success; official tagged GitHub `v2.2.39` Windows Portable ZIP and checked SHA256.
- Last operator LIVE observed **v2.2.37 STOPPING at 2026-10-27 08:36 Kyiv**, due to intentional shutdown, not evidence of a crash. Operator installation of v2.2.38 or v2.2.39 **not established** by this prior heartbeat.
- To install: stop old instance, back up entire original `Data`, extract the official Windows Portable ZIP into a fresh folder, transfer unchanged `Data`, never run both processes. Verify new version, 3/3 workers and collectors, independent Drive sync, actual publication (especially monitoring media article retry), preserve COMMITTED count and UNKNOWN quarantine. External HTTP 403 and ambiguous Telegram media remain open.
