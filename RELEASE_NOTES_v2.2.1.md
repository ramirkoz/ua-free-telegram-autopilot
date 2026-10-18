# UA FREE Telegram Autopilot v2.2.1 — Windows Secret Save Hotfix

**Operator testing prerelease.** Fixes the Windows access-denied error encountered when saving OpenRouter credentials under `Data/secrets.secure`.

- Atomic encrypted-credential replacement uses unique same-folder temporary files, preventing collisions between processes.
- Windows WinError 5/32/33 replacement failures receive bounded short retries rather than immediately raising.
- Encrypted previous credential file is retained if failure persists; no delete/truncate or weakened access permissions.
- Regression coverage for intermittent denial, persistent denial and first file creation.

**Testing:** Back up all `Data` and preserve prior 2.2.0 installation. Stop the old Autopilot, unpack this portable into a separate folder, migrate the `Data` directory, save OpenRouter settings, restart, and confirm configuration persists. Persistent denial may indicate Windows read-only/ACL or antivirus access and requires inspecting that external cause.

Editorial functionality remains the 2.2.0 evidence-first prerelease and still requires operator LIVE acceptance.
