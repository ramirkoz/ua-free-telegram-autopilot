# RC19 autonomous update protocol

The Autopilot runtime prepares an update but never replaces its own live files.

Flow:

`RUNNING -> QUIESCING -> READY_FOR_UPDATE -> helper applies update -> STARTING -> HEALTHY`

On failure after shutdown:

`FAILED -> ROLLING_BACK -> previous runtime + database backup -> ROLLBACK_OK`

The request contract is deliberately narrow: `request_id`, `target_version`, `sha256`, source metadata. The download location is derived from the fixed GitHub repository/release naming convention. Agent-supplied commands, arbitrary URLs and arbitrary target paths are not execution inputs.

Before handoff the runtime stops accepting new work, stops workers/collectors, checkpoints SQLite, creates a database backup, records update state, then launches the external helper. The helper verifies the archive hash, safe paths, version and runtime ABI, stages files outside the live tree, backs up replaced files, applies the release and restarts the program. A startup health marker is required; otherwise rollback restores the previous files and database backup.
