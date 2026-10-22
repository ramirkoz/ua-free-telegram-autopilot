# Autopilot 2.2.17 — operator-proven regional editorial and numeric QA corrections

**Operator baseline:** 2026-10-22 09:21 Kyiv. LIVE v2.2.16 RUNNING 3 workers/3 collectors; 490 COMMITTED delivery receipts of which 17 protected in independent archive, one UNKNOWN #66297 quarantined, 10 posts today (2/1/7). Sanitized operator SQLite uploaded to private Drive at 09:07. This is an observed operator state, not a test harness.

## Regressions corrected
1. **False loss of local public-transport notice #72839:** original Telegram `https://t.me/bezbaidy/42419` has a day glued to the preceding Cyrillic word: `транспорту22 жовтня`. Source QA `_number_tokens` dropped the number due to \w lookbehind; writer correctly wrote 22 and was rejected as hallucination, exhausting QA retries. Add bounded day+Ukrainian-month source split, without relaxing arbitrary invented number/model checks. Additionally compare day+named-month pairs in source and output: source route №23 cannot authorize a fabricated 23 October when the original date was 22 October. A 23-date in an otherwise matching candidate still fails without disabling the numeric QA. Existing rejected historical row is **not** requeued automatically.
2. **False-positive regional article #72838:** original `https://t.me/zaborzp/155080` forwarded all-Ukraine Russian military losses (2,250) without an actual Zaporizhzhia consequence. The daily totals failed prior narrow loss-roundup lexical pattern and were sent with image to Telegram #3383 on 2026-10-22 08:59 Kyiv. New opt-in civic exclusion recognizes documented national daily loss phrases based on original source body; ignores publisher branding. National losses without Zaporizhzhia source-owned civilian outcomes are blocked before AI and again before media/Telegram, including existing READY. Real local civil harm, municipal actions and local emergency response remain eligible. Does not blacklist whole source.
3. **Commercial output starvation:** in v2.2.16 operator last 2h had 32 processed/0 published, with documented weak hooks and B2B PRs. No proven code regression in this audit. **Do not loosen commercial editor thresholds merely to raise counts** or alter user 30min cadence. Separate source-yield/content review remains open.

## Safety unchanged
- Existing v2.2.16 freshness-first overload sorting and user publish intervals 45/30/5 minutes.
- Telegram media fidelity, no repost/replay, immutable COMMITTED receipt ledger including archive, UNKNOWN #66297 quarantine.
- v2.2.15 pre-media AI refusal-block, Windows SQLite restart/open recovery, sanitized hourly operator SQLite Drive snapshot.
- All source lists, operator `Data`, credentials, configured budget ($20/month OpenRouter in operator LIVE), and provider routing stay unchanged.
- Neither historical article #72838 nor #72839 is deleted, reposted, recovered or otherwise modified automatically.

## Release gates
Native GitHub PR CI on Ubuntu and Windows Python 3.11/3.12/3.13; independent Windows Portable release build and main merge; official main CI and asset digest/CRC verification. Real LIVE operator acceptance requires operator to install v2.2.17 with existing `Data` and observe channels and media with new telemetry.
