UA FREE Telegram Autopilot v2.0.0-rc84 — MANUAL TEST

Stability build based on RC83.
- Import from RC83 Data.
- Preserves durable Supervisor mirror/Telegram-report target only; old runtime state is not copied.
- Monitoring body sanitizer removes source/canonical/already-attached-media URLs before publish while preserving real action links.
- Supervisor reports Drive API and Telegram-report status in the UI.
- GitHub/Drive release sync is intentionally disabled until Windows validation.
