# UA FREE Telegram Autopilot 2.0.0-rc97

Focused UI responsiveness candidate based on RC96.

## Changes

- Reduces periodic Tk callback churn and refresh cadence for operational tabs.
- Skips heavy periodic view refreshes while the main window is minimized or hidden.
- Debounces notebook tab changes so rapid navigation does not stack refresh callbacks.
- Keeps slow reads in background threads and applies at most one completed view per UI pump.
- Renders Treeview rows in smaller time-sliced batches and avoids rewriting unchanged rows.
- Preserves selection while queue/editorial/history/AI tables update.
- Adds direct Tk event-loop lag measurement and exposes current/peak lag in Supervisor telemetry.
- Adds a distinct `UI_LAGGING` warning when the event loop repeatedly falls behind even if backend workers remain healthy.

## Preserved RC96 behavior

RC97 does not change channel policy, polling, collectors, workers, AI routing, credentials, dedupe, anti-slop, learning, publishing, monitoring live-now filtering, updater, migration or Telegram transport logic.
