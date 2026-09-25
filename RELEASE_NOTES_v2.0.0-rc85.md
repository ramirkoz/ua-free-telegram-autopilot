# UA FREE Telegram Autopilot v2.0.0-rc85

Cumulative operational-efficiency and editorial-control release on top of accepted RC84.

- Polling baseline raised from 5 to 15 minutes with a one-time migration for existing channels. The value remains editable per channel after migration.
- Added a generic pre-AI breaking-incident clustering lane. It can identify one fast-moving physical incident even when the exact facility/name is withheld, using time, location-bearing concepts, incident family and target class.
- Same-source and cross-source updates within a tight three-hour incident window can be deduplicated before editorial AI.
- Added runtime counters: pre_ai_duplicates, cluster_updates, ai_calls_saved.
- Added a visible “Редакторська черга” for editorial channels with rewritten materials that did not reach air.
- Editor can edit, approve to READY, publish now, or reject.
- Editorial actions are stored locally in editorial_actions and feed adaptive learning alongside Telegram reactions and audience performance.
- Manual edits become style-memory examples; approvals/rejections become topic-learning signals.
- Existing anti-slop, per-channel policy, source attribution, media gates and RC84 safety behavior are retained.
