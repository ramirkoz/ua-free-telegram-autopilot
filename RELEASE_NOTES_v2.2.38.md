# Autopilot 2.2.38 — AI/QA efficiency with hard factual safety

**Release criteria:** PR 4/4 CI, Windows native portable tests, Defender, merge to main, main 4/4 CI, main Windows signed build/Defender SUCCESS, official tagged GitHub ZIP and SHA256. Until then source is candidate only.

## Changes
- When an AI candidate fails ONLY the exact "unfinished trailing sentence" QA, a local function may remove a short final unfinished clause without fabricating a completion. It requires an existing ≥160-character body with ≥2 complete sentences, ≤140-character trailing fragment, no ambiguous trailing URL, and **full original validator success after the trim**. All factuality, source polarity, numbers/dates, length/structure, language, source-body attribution, prepublication and anti-slop gates remain unchanged. Unsupported numbers, stance flips, fabricated facts, or validation that still fails cannot become READY.
- Cloudflare `reasoning but no final content` bad-response failure now suppresses additional Cloudflare routes **only within the same AI task**, and never disables healthy providers or persists health damage. Every new task can retry as before; no provider credential/settings changes.
- The last-resort slow local Ollama/llama.cpp worker honors a bounded request-relative timeout rather than monopolizing a channel worker for 300 seconds on a 25s writer task; long explicit operator request times remain supported. Health probe timeout remains unchanged.
- New regression tests for short-tail rescue, never repairing facts or source polarity, malformed/long tail refusal, reasoning-only task suppression and bounded CPU timeout.

## What remains deliberately excluded
- This release does not hide editorial QA, relax rules to increase posts, alter model IDs, add paid APIs, change operator source lists/roles, change Telegram scheduling, lower provider budgets or replay old delivery receipts.
- Design Milk 403, Rest of World 403, Campaign Brief 522 and unknown split-media ownership remain external/unproved limitations.

## Operator update
- Latest verified operator LIVE: 2.2.37 at 2026-10-26 17:02 Kyiv, RUNNING, 3/3 workers/collectors, independent Google Drive `autopilot-oauth`, 55 posts today (9/12/34), 749 COMMITTED, 1 FAILED, one quarantined UNKNOWN.
- Back up full Data, stop old 2.2.37, extract official Windows v2.2.38 Portable ZIP to a separate directory, import unchanged Data, use only one running copy, retain 2.2.37 folder as rollback.
- Verify actual 2.2.38 LIVE, 3/3 workers/collectors, original sources (36/18/57), intervals (45/30/5 minutes), OpenRouter spend caps ($3/day; $20/month), Drive writes, delivery ledger and unchanged UNKNOWN safety. Check new `truncated AI tail rescued by full QA` log events against source/posted facts before concluding a publication benefit.
