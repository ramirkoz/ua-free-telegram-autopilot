# Autopilot v2.1.18

- **Restored original reporting from connected independent Zaporizhzhia newsrooms** in operator channel `ЗАПОРІЖЖЯ | ГРОМАДИ`: `ЗаБор`, `БЕЗ БАЙДИ`, `5 РЕДАКЦІЯ`, `ЗАПОРІЖЖЯ.INFO`, `INFORM.ZP`, and others are candidates for editorial review instead of being hard-rejected as non-government accounts.
- One-time guarded data migration changes `monitoring_source_policy` from `institutional` to `connected_original` **only** when channel name is exactly `ЗАПОРІЖЖЯ | ГРОМАДИ`; preserves operator choices, other channels and denylist.
- Unverified reports attributed to subscribers, readers, locals or eyewitnesses remain rejected; reporting with explicit independently verified agency confirmation may be considered.
- Native forwarded messages, configured denied origins, live-only air warnings, incident postfactum checks and duplicate gates remain active. This release does not blanket-approve any outlet's stories.
- Regression tests cover newsrooms, rumor formats, verified factual attribution, forwarded posts and isolated migration.
- Install Windows Portable in a new folder, migrate only Data from v2.1.17 after backup; keep old folder as rollback. Confirm original newsroom publications and noise-free moderation with LIVE after deployment.
