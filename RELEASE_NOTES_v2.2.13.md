# Autopilot 2.2.13 — SQLite startup recovery, durable delivery receipts, private analysis snapshots

**Safety fix.** A pre-existing Data SQLite database opens normally so SQLite can recover hot journals; a real read/recovery failure is reported visibly and never causes automatic first-run import. Repeated launch after successful import skips the migration dialog.

**Retention fix.** Article deletion during seven-day cleanup now copies delivery journal rows to independent `delivery_receipt_archive` before the foreign-key CASCADE. Both delivery summary and SHA-256 fingerprint include archived receipts. There is **no** Telegram replay, no restoration of already-purged history and no change to operator cadence.

**Drive operator analysis.** A nonblocking background worker starts after ten minutes, makes a transactionally consistent SQLite backup, exports only an allowlisted diagnostic schema (public source and article text, processing stages, jobs, delivery receipts; excludes credentials, keys, private channel chat ID and raw error bodies), validates it, and uploads `operator_data_current.sqlite3` to the already configured private LIVE Google Drive folder. It overwrites the same Drive file by name hourly after success and retries after errors. It is **not** a full restorable Data backup. Upload requires the existing Drive connector/credentials.

**Important limitations.** Two source archives supplied by the operator show 466 COMMITTED in 2.2.11 and 461 in a later 2.2.12 backup: ten old receipts were lost due to past cascaded retention while five new receipts were added. This release protects future records but cannot invent the deleted receipts from 2.2.12 alone. Do not replace working Data with a backup, repeat the first-run import, or retry UNKNOWN Telegram article #66297 without manual reconciliation.

**Verification:** local targeted SQLite/restart/retention/export tests passed. GitHub PR CI, native Windows packaging and operator LIVE acceptance are independent gates.

**Release regression fixes:** Windows native CI found a WinError 32 temp-file lock because Python's sqlite3 connection context manager does not close the connection; v2.2.13 now explicitly closes every connection before deleting or replacing snapshot files. The operator test DB produces a ~34 MB diagnostic export, so Drive uploads of larger SQLite diagnostics use a single-request resumable session. JSON telemetry retains its fast route.
