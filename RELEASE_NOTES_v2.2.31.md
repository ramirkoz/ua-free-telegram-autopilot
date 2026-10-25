# Autopilot 2.2.31 — source-grounded daily attack event identity

Date: 2026-10-25. **Feature branch / PR candidate**, NOT an official GitHub main release and NOT installed on the operator until separately verified. CI and signed native Windows build are independent gates.

## Incident and evidence
- On Oct25, three different regional Telegram sources caused three posts at 11:26:19 (article #79194, Telegram #3699), 11:31:31 (#79198, Telegram #3705) and 11:36:42 (#79195, Telegram #3709) about **October 24 attacks in Zaporizhzhia city and raion** with **four injured (ages 43, 60, 14, 61)**. Two articles explicitly mention **832 attacks**; the first police-source digest omits the total, so a raw number-matcher misses it.
- Evidence from read-only operator `operator_data_current.sqlite3` snapshot (2026-10-25 14:16 Kyiv) and official LIVE `2.2.30` status at 15:15 (3 workers + 3 collectors, 22 cumulative posts, 678 committed, UNKNOWN #66297 quarantined). Historic triple Telegram posts cannot be deleted/replayed automatically.

## Change
- New `regional_daily_event_231.py`: source-only original title/raw text, timezone-aware original source-publication timestamp, regional + daily-scope evidence, date of **reported event** (not scrape/discovery/post time), strike total, aggregate injury total and independently listed victim ages. Names of publishers, article URLs, AI final captions and news template scaffolding do not establish identity.
- High-confidence same-event duplicate if shared regional report day AND compatible daily casualty / attack totals or corroborating four victims from their age signatures. Additional evacuation/damage commentary alone is not a new attack. A genuine amended injury/strike total with original-source correction markers is an **UPDATE**, never an automatic duplicate. If event dates, geography or facts conflict or are insufficient, fail open to the downstream existing independent editorial safety gates.
- Integrated into `EventFingerprintDedupeEngine` before generic semantics for pre-AI candidates and published-history at the final prepublish gate; integrated into **COMMITTED-only** `event_memory.py` as `regional_daily_attacks`, retains stable `event_id` on genuine published updates. No global `dedupe_shadow` blocking flip. Cross-channel matching remains isolated by channel.
- Regression suite `tests/test_2231_regional_daily_event_identity.py`: three operator paraphrases, absent 832 figure on police summary, positive two-sentence/age-based identity, changed day, unverified source time, unrelated single-town attack, inconsistent named victim ages, improved source facts, confirmed count UPDATE, fabricated AI claim, UNKNOWN/FAILED receipt no-proof, archived COMMITTED as valid authority.
- User's source set (CTRL+UA 36, ПРОДАНО! 18, ГРОМАДИ 57), 45/30/5-minute publication intervals, per-channel editor settings, all AI budgets and provider routes, unmodified local original Data and pending editor queue, Telegram already posted receipts and UNKNOWN quarantine remain untouched.

## Verification and handoff
1. PR CI complete (Ubuntu and Windows Python 3.11/3.12/3.13) and native Windows PR preview/Defender before main merge.
2. After green: squash merge into main, verify tag v2.2.31 and **official main Windows Portable release workflow** separately. Never assert official artifact before GitHub reports it.
3. No unattended Windows deployment. Manual separate-folder operator Data backup + import and stop old version; preserve isolation. After operator installs, confirm LIVE 2.2.31 and review naturally occurring duplicate cases versus source and real public channel; also count false-positive suppression and legitimate changed-casualty follow-up.
4. Next version **2.2.32** media and source-yield diagnostics, not folded into this event-identity release. No paid API pilot, no local machine tests on the operator, no historical Telegram replay.
