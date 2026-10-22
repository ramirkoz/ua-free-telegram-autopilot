# Autopilot 2.2.19 — cross-source repatriation dedupe and local relevance gate

22 October 2026. Regression based on source-owned original text from sanitized operator SQLite plus operator screenshots.

## Fixed
- Cross-source duplicate of one national military-remains repatriation announcement: BEZ BAIDY article #74213 / Telegram 13:30, then Zabоr ZP article #74233 / Telegram 13:53. Both reported the return of 252 bodies, but source wording, photos and headlines differed. The prepublish trace already found #74213 as nearest publication (5 shared concepts/0.50) yet failed to classify the event as identical.
- New conservative central same-event matcher anchored in original-source return/remains/service status, the identical count immediately associated with remains, distinct publishers and confirmed times within six hours. Applies before rewrite and during durable published-ledger final prepublication checks; never relies on image identity, URL, or rewritten caption.
- New opt-in monitoring-source civic gate rejects national repatriation tallies without an explicit local anchor. A Zaporizhzhia-branded source is not a Zaporizhzhia civic event. Existing verified local impacts remain admissible.
- Explicit material follow-ups, different figures, later rounds, absent reliable timezone and other unrelated incidents remain separate. Per-channel opt-in protects editorial channel behavior.

## Regression
- `tests/test_2219_cross_source_repatriation.py` covers both operator articles, minimal durable ledger, pre-AI and prepublish civic gates, same-vs-different event and negative control cases.

## Operator safety
- No changes to operator Data, source lists, cadence, provider preferences, $20 OpenRouter monthly cap, receipt archive, channel settings, media pipeline or Telegram UNKNOWN #66297.
- Already published Telegram duplicates are not deleted, edited or replayed automatically.
- Built source/PR is not evidence of operator LIVE acceptance. Official native Windows Release workflow must pass, generate SHA256SUMS and publish tag v2.2.19 before installation.
