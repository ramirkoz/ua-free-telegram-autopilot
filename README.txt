UA FREE Telegram Autopilot v2.0.0-rc87 — MANUAL TEST

RC87 is based on RC86.

Migration repair:
- legacy Data is first copied through SQLite online backup into a private temporary snapshot;
- the importer never works directly against the selected RC85 database;
- source==target is safe because import reads the private snapshot;
- current RC85 channel settings, dedupe settings, attribution settings, Facebook page selections and source legacy_config_json are preserved;
- channel policy source-body attribution settings are preserved;
- migration remains transactional and restores the previous V2 database if destination replacement fails.

RC86 source text-link cleanup and cross-source duplicate fixes are retained.
