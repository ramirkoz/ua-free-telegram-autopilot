# UA FREE Telegram Autopilot 2.0.0-rc103

RC103 applies the audited scientific/news channel profile and bounds the live database/UI to the operator's seven-day working horizon.

- Scientific/news editorial channels are tuned through visible channel settings, selected by persisted role (`scientific_news`) rather than channel name or ID.
- Target mix: AI 38%, robotics 18%, defense/Ukraine tech 14%, cybersecurity 10%, hardware 10%, science/space 7%, medicine/biology 3%.
- Publishing window 08:00–20:00, minimum 45 minutes between posts, maximum two posts per publish cycle, 30-day published-event dedupe window, and 450–600 character target copy.
- The editorial mix is persisted in visible per-channel settings/policy text instead of hidden global logic.
- Editorial review and operational queue views show only the last seven days; history view is also bounded to seven days.
- UI queue/history SQL no longer loads full article bodies, rewrite text, media JSON and layouts for hundreds of rows just to render list columns.
- Startup maintenance archives unfinished work older than seven days, removes stale jobs, prunes audit telemetry older than seven days and compacts heavy payloads after their operational/dedupe usefulness expires.
- SQLite receives recent-row indexes, `PRAGMA optimize`, WAL checkpointing and conditional VACUUM when reclaimable pages are materially large.
- Supervisor database telemetry now reports database size, freelist ratio, seven-day operational row count and stale unpublished rows.

The latest live telemetry available while building RC103 was still emitted by RC101 and showed a UI event-loop peak lag of about 14.7 seconds plus heavy AI/provider pressure. RC103 therefore does not claim RC102/RC103 live acceptance until the new build is actually run.
