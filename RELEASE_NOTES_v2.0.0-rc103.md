# UA FREE Telegram Autopilot 2.0.0-rc103

RC103 applies the audited scientific/news channel profile and aligns the live database/UI with the operator's seven-day working horizon.

- Scientific/news editorial channels are tuned through visible persisted channel settings, selected by the existing `scientific_news` role rather than channel name or numeric ID.
- Target mix: AI 38%, robotics 18%, defense/Ukraine tech 14%, cybersecurity 10%, hardware 10%, science/space 7%, medicine/biology 3%.
- Publishing window 08:00–20:00, minimum 45 minutes between posts, maximum two posts per publish cycle, seven-day published-event dedupe horizon, and 450–600 character target copy.
- The editorial mix is persisted in normal per-channel settings/policy text instead of hidden channel-name business logic.
- Editorial review, operational queue and history views are bounded to the last seven days and use narrow list-column SQL instead of loading full article blobs.
- Live database retention is also seven days: expired articles are deleted together with article-owned jobs, feedback, editorial actions, rewrite revisions and repost rows via foreign-key cascades. Learning already uses a seven-day window, so the storage horizon now matches the product horizon.
- Audit telemetry older than seven days is removed; recent-row indexes, `ANALYZE`, `PRAGMA optimize`, WAL checkpointing and conditional `VACUUM` keep SQLite compact.
- The Tk UI no longer rebuilds every hidden tab every 2.5 seconds. Home plus only the currently visible dynamic tab are refreshed; switching tabs triggers an immediate refresh of that tab.
- Supervisor database telemetry reports database size, freelist ratio, seven-day operational row count and stale rows.

Telemetry evidence that motivated the UI/database part came from the latest live snapshot available during development, still RC101: UI event-loop peak lag reached about 14.7 seconds, with 26 active jobs and large review/history churn while all tabs were being rebuilt every refresh cycle. No fresh RC102 telemetry had reached the Drive live mirror yet, so RC103 runtime acceptance remains a live test rather than a CI inference.
