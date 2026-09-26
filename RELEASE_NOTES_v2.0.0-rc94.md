# UA FREE Telegram Autopilot v2.0.0-rc94

Windows validation repair after RC93.

## Fixed

- Restores missing Gemini, NVIDIA, Groq and Cloudflare credentials from validated older Autopilot portable builds found around the selected migration source and common portable locations such as Desktop, Downloads and OneDrive.
- Preserves all non-empty current credentials, including the current Codex state, while filling only missing provider values.
- Keeps credential recovery marker compatibility with existing RC89/RC90 regression coverage.
- Adds a regression for the real split-location scenario where an accepted older build is on Desktop and the new portable is launched from Downloads.

No Google Drive or ProductVault synchronization is performed before live Windows validation.
