# UA FREE Telegram Autopilot v2.0.0-rc52

RC52 hardens two production failure modes observed on live CTRL+UA monitoring: heavily paraphrased duplicates of the same concrete event and a single slow source extending an entire collection cycle.

## Duplicate protection

- Added a cross-source event fingerprint layer on top of the existing semantic duplicate guard.
- The new matcher uses normalized concept roots, event-family anchors and compatible numeric evidence rather than requiring the same literal phrases.
- Biomedical research reports receive a narrow high-precision lane for independently rewritten coverage of the same experiment.
- The final pre-publication check now compares READY material against at least seven days of PUBLISHED history, even when the normal ingest dedupe window is shorter.
- Existing exact URL/hash/code rules and the RC49 community-notice guard remain intact.

The regression fixture includes the observed case where one report says human neurons occupied more than 90% of a mouse cortex and another says a human cortical transplant occupied about 92%: these are now treated as one event.

## Slow-source isolation

- Added an aggregate 70-second channel collection budget.
- Sources that finish inside the budget are committed normally.
- A late source is recorded through the existing source-health/cooldown mechanism and its eventual result is discarded instead of blocking the whole monitoring channel.
- Individual collectors retain their own transport and enrichment deadlines.

No database migration or user-setting reset is introduced by RC52.
