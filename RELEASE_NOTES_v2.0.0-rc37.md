# UA FREE Telegram Autopilot v2.0.0-rc37

## Final manual baseline for remote operations

RC37 is intended to be the last version that needs to be installed manually for the current remote-control architecture. It includes the RC36 editorial-media fail-closed fix and upgrades the control plane to the same transaction model proven in KONTUR.

### Remote self-update transaction

- The live runtime no longer has to stop every worker/collector successfully before an approved update can proceed.
- `UPDATE_QUIESCE_TIMEOUT` is removed from the update handoff path.
- The detached updater is launched while the current application is still healthy.
- Package download/copy, SHA-256 verification, safe ZIP extraction and ABI/release validation happen before the running parent is touched.
- Only after preflight succeeds may the detached updater terminate the exact parent PID. It never uses a process-tree kill that could terminate itself.
- A consistent SQLite backup is created before handoff and validated with `PRAGMA quick_check`.
- The target release is started under a fresh Supervisor health gate. Success requires the requested version, DB OK and, when channels are enabled, RUNNING runtime with the expected workers and collectors.
- Target startup is retried up to three times.
- If the target cannot pass the health gate, program files and the database are restored.
- Rollback is not called successful merely because files were copied back: the previous version must itself restart and pass the same fresh Supervisor/DB/runtime verification.
- Preflight failure leaves the current known-good application running.

### Telegram agent reporting

- Existing replay-safe delivery remains based on `report_id` and `agent_telegram_ack.json`.
- ACK is written only after Telegram returns a message ID.
- RC37 accepts both the legacy preformatted `message` and a structured remote-agent payload.
- Structured reports are formatted locally in Ukrainian as `Autopilot · Перевірка агента` with status, version, runtime, channels, DB, AI, queue, publications, detected issues, fixes, update result and next action.
- CRITICAL/RECOVERY and ordinary status reports use the same durable delivery path and retry protection.
- Chat resolution still refuses to guess when multiple private chats are visible to the bot.

### Editorial media safety

- Includes the RC36 fix that removed the raw first-image fallback from editorial publication.
- If semantic/rubbish validation cannot positively validate media, an editorial post is text-only rather than publishing an unrelated follow/subscribe/banner image.
- Monitoring-channel source galleries are not changed by this rule.

### Compatibility

- Existing `Data`, channels, sources, publication history, feedback, credentials and per-channel source-attribution settings are preserved.
- Update overlays are still prohibited from containing `Data`.
- Remote agents may request only a version and SHA-256; arbitrary commands, paths and executable URLs are not accepted.
