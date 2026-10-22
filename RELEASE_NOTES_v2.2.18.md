# Autopilot 2.2.18 — cross-source traffic dedupe and transient road-news freshness

Operator baseline: 2026-10-22 10:49 Kyiv, LIVE v2.2.17 running, three channel workers and collectors healthy, 501 COMMITTED receipts (17 archived), UNKNOWN #66297 quarantined.

## Root causes and fixes
1. **Double Telegram publication of one traffic event:** after original local article #73290, from `https://t.me/ZapoLife/112024` (Telegram #3388 at 10:06), the same DniproHES bridge/dam ДТП and traffic congestion from Kakhovska ring was published again as #73267 from `https://t.me/info_zp/170170` (Telegram #3400 at 10:49). The final prepublish trace **recognized #73290 as the nearest previous publication** but did not cross the generic concept threshold (only 5 shared concepts / 0.50, no named entity). Short rewriting and differing video watermarks bypassed phrase dedupe. **2.2.18** adds a conservative same-traffic-event rule in the existing central fingerprint matcher at both pre-AI and prepublish: different sources; original-source crash AND congestion; identical dam/bridge type, matching named street approach, source/published timestamps within two hours; no conflicting travel directions, distinct second accident or reopened road. Previous source URLs not required to match. Published-event ledger comparisons work with its minimal fields. No generic same-location blocking, no ban of any publisher, no video fingerprint-based guesses or Telegram deletions.
2. **Transient road notice aged before send:** #73267 originally published at 08:56 and sent at 10:49. A temporary jam cannot be assumed current nearly two hours later. For `[LIVE_NOW_RC96]` monitoring channels only, veto source-owned current crash+congestion bulletins older than 75 minutes at both pre-AI and final Telegram publication gate. Exempt source-owned official enduring road closures/reroutes, traffic clearance updates and stable civic-service news. No source timezone or source date means no guessed expiration. Operator channel publish intervals untouched.

## Regression verification
- `tests/test_2218_traffic_cross_source_operator_regression.py` recreates the real 10:06/#73290 and 10:49/#73267 pair and minimal published ledger.
- Negative cases: same-source, road type only, different approach, opposite explicit direction, reopening and traffic cleared, second explicitly separate ДТП, next-day accident, official route restriction, no timestamp, non-traffic news.
- All 2.2.17 regression and native Windows tests must succeed on Ubuntu and Windows Python 3.11/3.12/3.13 and official main release ZIP CRC/SHA-256 before operator installation. Do not call a PR build the official release.

## Operator safety and limitations
- Do not change existing operator Data, source setup, editorial policies, cadence (CTRL+UA 45m, ПРОДАНО! 30m, regional existing setting), provider preferences, $20 monthly OpenRouter budget, media integrity or local monitoring source lists.
- Preserve published receipt ledger and archived COMMITTED counts, never retry UNKNOWN #66297.
- Posts #3388/#3400 already published; **no automatic deletion or replay**.
- Known unresolved: ПРОДАНО! low content fit/yield, QA `qr` false positives unproven until AI source/candidate paired evidence, external HTTP403s, long-lived READY backlog. Not silently reworked in this narrow release.
- Native operator LIVE v2.2.18 acceptance remains pending until the user installs from the official ZIP and fresh Google Drive telemetry confirms real running version, clean restart, media and nonduplicate traffic outcomes.
