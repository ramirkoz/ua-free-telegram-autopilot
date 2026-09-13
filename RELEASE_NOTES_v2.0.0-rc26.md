# UA FREE Telegram Autopilot V2.0.0-rc26

## Compact portable + first-run AI bootstrap

- Removed the 400+ MB unpacked Codex runtime from the base Windows portable.
- The application now keeps Codex as a separate AI runtime under `Data\ai_runtime` and installs it automatically on first launch when it is missing.
- First-run setup uses the bundled portable Python/pip and does not require a system Python installation.
- If the AI download cannot complete, the application still opens; Codex can be installed on a later launch when connectivity is available.
- The base portable still contains all non-AI runtime dependencies required to start the UI, database, Telegram, media and migration layers.
- Release CI now verifies the compact base package, performs a real Codex bootstrap into a temporary Data directory, runs native Windows GUI smoke, scans with Microsoft Defender, and rejects oversized packages.
- RC24/RC25 application behavior is otherwise preserved.
