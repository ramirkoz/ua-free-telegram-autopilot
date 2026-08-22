# UA FREE Telegram Autopilot 0.1.0-rc34

## Critical Windows launcher fix

RC33's generic release workflow produced a broken Portable launcher by copying `pythonw.exe` to `UA_FREE_Telegram_Autopilot.exe` without supplying `app.py`. Double-clicking the published EXE therefore did not start the application.

RC34 keeps the RC33 editorial/source-priority changes and fixes only the Windows packaging path:

- adds a native Windows bootstrap EXE that starts the bundled `pythonw.exe app.py` from the portable folder;
- displays an explicit Windows error dialog if the runtime or entrypoint is missing;
- keeps the launcher alive while the GUI process is running;
- adds a release smoke test that physically launches the packaged EXE on Windows, verifies the process remains alive and verifies that the SQLite database is initialized;
- release publication is blocked if that smoke test fails.

RC33 editorial changes retained: CTRL+UA audience/newsworthiness gate, stronger event dedupe, source priority 1-100, media-first Telegram formatting, and video-link fallback behavior.
