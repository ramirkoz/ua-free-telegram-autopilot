# UA FREE Telegram Autopilot v2.0.0-rc47

## Responsive GUI refresh boundary

RC47 fixes a Windows GUI freeze where the Autopilot runtime could continue collecting and processing in background threads while the Tkinter window stopped responding.

- Moves periodic data collection for Home, Channels, Queue, History, AI, Statistics/Learning and Supervisor off Tk's main thread.
- Marshals only final widget updates back to the GUI thread.
- Prevents overlapping background refresh workers for the same view.
- Uses short query-only SQLite reads for periodic queue/history/home snapshots so normal runtime writes cannot stall the window.
- Keeps runtime start/stop, collectors, workers, editorial pipeline, publisher/media rules, local AI fallback, telemetry, Supervisor and signed updater behavior unchanged.
- Logs failed background refreshes without stopping the Autopilot runtime.

This is a GUI responsiveness release. Existing V2 `Data` remains compatible and can be copied into a fresh RC47 Windows Portable folder.
