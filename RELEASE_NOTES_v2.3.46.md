# UA FREE Telegram Autopilot 2.3.46 — no duplicate donor threads in «ГРОМАДИ»

20 November 2026. **Owner-provided LIVE screenshot + READ-ONLY telemetry:** on installed v2.3.43 the monitoring channel published 2 back-to-back, near-identical emotional childhood/war messages from the same donor. Source items `https://t.me/mih_gromada/4762` and `/4763`, operator article IDs `107571`/`107572`, output message IDs `5409` at 10:36:18 Kyiv and `5410` at 10:41:31 Kyiv. The 5-minute posting cadence functioned; the source/event editorial selection did not. Prepublish event trace for second item chose unrelated article `107386` as nearest rather than first same-source post.

## Fix

1. New `monitoring_no_event_2346.py`: deterministic rejection of child/war sentiments and generic Children's Day calendar greetings without a completed or scheduled, source-confirmed civic action. It examines original source title/body, not AI copy, excludes genuine local events, help, evacuations, safety updates, aid and services. No model, token or provider changes.
2. Hook in `monitoring_civic_quality.civic_relevance_exclusion`, already invoked **before AI via live_now_exclusion** and **at READY/prepublish via hard_editorial_reject**. Existing `[LIVE_NOW_RC96]` opt-in remains intact.
3. In monitoring `event_fingerprint_same_event`, keep material update protection first; then a same-source near-time reflective-sequence guard and a conservative original-Telegram adjacent-message high-overlap guard. The latter requires same source, same Telegram chat, consecutive IDs (difference <=2), <=2h source time, >=6 shared meaningful word stems and >=60% containment, unchanged source numbers and no opposing phase. No blanket same-source ban.
4. Read-only `published_event_ledger` query joins `articles` to recover original source URL and time during prepublish comparison. No schema migration or operator data edit.
5. 2.3.46 regression tests cover screenshot originals, pre-AI/READY veto, ledger-shaped source records, real distinct service/evacuation updates, different donor/older date and source-message continuity. SQLite replay of 753 **already published** monitoring articles: exactly 3 no-event Children's Day messages newly flagged; 0 generic adjacent-source unexpected matches. This validates sample safety, not all future inputs.

## Operational invariants

No automatic install and no operator Data/Telegram mutation; current operator v2.3.43 until manually updated. Preserve 2 `UNKNOWN` delivery receipts and credential config, publishing cadence 30/30/5 min, OpenRouter $3/day $20/month, and all three channel assignments. 2.3.46 includes code from official 2.3.45 (and 2.3.44). Before release require independent CI 4/4 and native Windows/Defender with ZIP CRC+SHA256 verification. Publish first, then manual operator installation and check two real new monitoring posts.
