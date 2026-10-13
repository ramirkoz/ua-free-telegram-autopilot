# Autopilot 2.1.6 — READY buffer and queue monitoring

- Differentiate an intentional, healthy two-item READY buffer pause during MIN_INTERVAL from a genuinely stalled processing worker.
- Preserve STALLED when heartbeat is stale, READY is not publishable, or no recent publication exists.
- Add four regression tests covering healthy buffering and genuine stalls.
- Preserve editorial source-integrity requirements, monitoring exclusions, duplicate safeguards, media gates, user Data, delivery journal, and retry limits.
- Known limitations: This patch does not yet resolve the ПРОДАНО! low publication throughput, unavailable FastCompany #48819 image, or all monitoring source provenance limitations. Live editorial acceptance is pending.
- Manual Windows Portable upgrade requires retaining Data/credentials and rollback to 2.1.5. CI and native build are release gates, not evidence of accepted live output.
