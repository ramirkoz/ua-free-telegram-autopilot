UA FREE Telegram Autopilot v2.0.0-rc88 — MANUAL TEST

RC88 fixes the actual RC85 -> newer V2 migration path.

- When an old portable/Data contains both telegram_autopilot.sqlite3 and telegram_autopilot_v2.sqlite3, V2 now always wins.
- Current V2 databases are carried forward as an exact SQLite snapshot, not reinterpreted through the legacy converter.
- Channels, sources, queue/history, published records, feedback/learning and current settings stay intact.
- The source database is never modified.
- True old legacy databases still use the legacy converter.
- RC86 source text-link cleanup and duplicate fixes are retained.
