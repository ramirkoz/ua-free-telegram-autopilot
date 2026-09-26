# UA FREE Telegram Autopilot v2.0.0-rc91

Emergency Windows startup-hardening candidate after RC90 live first-run failure.

## Fixed

- First-run import is no longer hosted by a withdrawn/hidden Tk root. A visible startup window stays on screen while interactive migration begins.
- The main window is explicitly deiconified, raised and focused after construction.
- Windows single-instance protection now uses a named kernel mutex instead of holding a lock file open inside the portable directory.
- Native/Python crash diagnostics are persisted to `Data\logs\v2\crash.log` via `faulthandler`, `sys.excepthook` and `threading.excepthook`.
- Startup telemetry now records `UI_READY`, `MAINTENANCE` and `RUNTIME_READY` stages.
- Automatic update polling is deferred for 30 seconds after runtime readiness so update handoff cannot race a fresh GUI/runtime start.
- The second-launch message now explains that the first launch may still be completing instead of implying that a usable window must already exist.

## Preserved

- RC90 credential migration and polling repair.
- anti-slop and channel-specific editorial/dedupe settings.
- exact-post Telegram media ownership.
- local learning/editorial review.
- signed updater and existing Data/Tools migration contract.

## Acceptance

This is a testing candidate until real Windows first-run and sustained runtime behavior are confirmed by the user. GitHub/CI success alone is not user acceptance.
