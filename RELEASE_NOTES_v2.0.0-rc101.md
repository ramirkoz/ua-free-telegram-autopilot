# UA FREE Telegram Autopilot 2.0.0-rc101

Focused editorial-state and migration hardening on top of RC100.

- Human approve/edit/reject now resolves the editorial review item in UI; approved material continues through the normal READY publication path.
- Manual approve/edit refuses `TELEGRAM_OUTCOME_UNKNOWN` to prevent blind duplicate delivery.
- Completed `final_text` is preserved across media recovery, startup backlog recovery and Telegram media sanitization.
- Append-only `rewrite_revisions` records durable rewrite/editor revisions.
- First-run import preserves completed rewrites, `editorial_actions`, rewrite revisions and migration markers; only rows without a completed rewrite are reprocessed.
- Legacy RC98 commercial-profile startup repair is frozen and no longer rewrites operator channel policy or source configuration.
- Human-approved READY rows are protected from stale-age retirement.
- RC101 regression tests cover live approve/reject semantics, unknown-delivery guard, rewrite preservation and import durability.
