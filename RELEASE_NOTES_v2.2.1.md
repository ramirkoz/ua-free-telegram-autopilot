# UA FREE Telegram Autopilot v2.2.1 — Windows Secret Save Hotfix

**Operator testing prerelease.** Fixes the Windows access-denied error encountered when saving OpenRouter credentials under `Data/secrets.secure`.

- Atomic encrypted-credential replacement uses unique same-folder temporary files, preventing collisions between processes.
- Windows WinError 5/32/33 replacement failures receive bounded short retries rather than immediately raising.
- Encrypted previous credential file is retained if failure persists; no delete/truncate or weakened access permissions.
- Regression coverage for intermittent denial, persistent denial and first file creation.

**Testing:** Back up all `Data` and preserve prior 2.2.0 installation. Stop the old Autopilot, unpack this portable into a separate folder, migrate the `Data` directory, save OpenRouter settings, restart, and confirm configuration persists. Persistent denial may indicate Windows read-only/ACL or antivirus access and requires inspecting that external cause.

Editorial functionality remains the 2.2.0 evidence-first prerelease and still requires operator LIVE acceptance.

## CTRL+UA visual duplicate gallery hotfix

- Actual reported incident: Tom's Hardware, article 63224, Telegram messages 1387–1389 showed near-identical gallery artwork three times.
- The Telegram media preparation deduplicator now compares genuine image pixel crops in addition to its existing resize/compression signatures. It keeps different images and never compares video payloads as pictures.
- Tests cover cropped same-illustration variants, unrelated illustrations and the actual final `remove_visual_duplicates` function used before upload.
- This is a test build. Verify on subsequent real Tom's Hardware / CTRL+UA posts, rather than assuming historical publications are automatically corrected.
