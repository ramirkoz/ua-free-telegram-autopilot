# Autopilot 2.1.7 — Channel-configured source trust and stale ingest gating

## Improvements
- Universal pre-ingest freshness check uses each channel's persisted `max_age_hours` and handles ISO 8601 plus RSS/RFC 2822 dates. Clearly historical *new* items never enter the operational articles/AI queue. Records with unknown or ambiguous dates retain existing safety rules. Already-known source items still refresh their media and layout.
- Monitoring source-origin policy is a **per-channel** setting, not a named-channel rule in the engine. Added two operator-visible modes in the channel policy UI:
  - `institutional` (default): preserve the previous strict Telegram institutional source-name gate;
  - `connected_original`: allow original posts from the operator's connected sources regardless of institutional name, while blocking native forwards and retaining reader-rumour, private notice, unsettled threat, source-context, and other monitoring gates.
- SQLite policy migration preserves existing Data, all existing channels and decisions, and the conservative `institutional` mode until changed by the operator.
- Regression tests cover channel-dependent freshness, RSS timestamps, unknown dates, institutional vs connected-original trust, native forward blocking, rumour safety, and DB persistence.

## Operator action / limitations
- For a monitoring channel intentionally configured to accept *original posts from all its connected sources*, select **Налаштування каналу → Політика → Політика походження моніторингових джерел → Оригінали всіх підключених джерел**. Do this only for sources you trust: the engine does not independently verify claims by a news aggregator.
- This release does **not** automatically infer primary official provenance from reposted articles; it does not enable unverified original claims from arbitrary sources unless that channel explicitly selects the mode.
- Source-date checks do not make an ambiguous undated source trustworthy. Source freshness and editorial verification still apply downstream.
- No mass requeue of rejected items; no manual data reset. Existing decisions and delivery journal are retained.
- Full production editorial acceptance, source media recovery for unresolved commercial articles, quality of published captions and throughput recovery require live operator verification. Signed automatic Windows update workflow has a known failure; use manual Portable update while preserving Data and the previous version for rollback.
