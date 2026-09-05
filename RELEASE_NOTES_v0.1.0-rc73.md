# UA FREE Telegram Autopilot v0.1.0-rc73

RC73 completes the restoration of manual per-channel controls started in RC72.

## Per-channel fine settings are visible again

Each channel keeps its own manually configured:

- mission / purpose;
- audience;
- inclusion / selection rules;
- exclusion / rejection rules;
- writing structure;
- tone and style;
- positive and negative examples;
- media policy;
- target post length;
- selector prompt additions;
- writer prompt additions;
- content language direction;
- media-first settings;
- editorial/monitoring mode and scheduling;
- **operator-defined editorial categories and weights**.

Editorial weights are relative targets. Weight `0` forbids automatic publication of that category. An empty list means the weighted balance gate is disabled.

Monitoring channels keep their stored weights but do not apply them while in monitoring mode. Monitoring still bypasses Editorial Value, thematic-interest scoring and thematic balance, and uses only the explicit per-channel inclusion/exclusion policy plus universal technical safeguards.

## Architecture rule

Channel-specific editorial taste is not hardcoded under the hood and is never inferred from a channel name. The shared engine contains only universal collection, dedupe/clustering, language/media infrastructure, Fact Guard, scheduling, QA, monitoring/editorial branching and the universal Editorial Value Gate for editorial channels.

RC73 retains RC69 media-first enrichment, RC70 mixed Ukrainian/Russian source support, RC71 contextual freshness/deferred media behavior and RC72 per-channel policy restoration.
