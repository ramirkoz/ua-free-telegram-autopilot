# UA FREE Telegram Autopilot 2.0.0-rc97

Focused responsiveness and monitoring-quality candidate based on RC96.

## UI responsiveness

- Reduces periodic Tk callback churn and refresh cadence for operational tabs.
- Skips heavy periodic view refreshes while the main window is minimized or hidden.
- Debounces notebook tab changes so rapid navigation does not stack refresh callbacks.
- Keeps slow reads in background threads and applies at most one completed view per UI pump.
- Renders Treeview rows in smaller time-sliced batches and avoids rewriting unchanged rows.
- Preserves selection while queue/editorial/history/AI tables update.
- Adds direct Tk event-loop lag measurement and exposes current/peak lag in Supervisor telemetry.
- Adds a distinct `UI_LAGGING` warning when the event loop repeatedly falls behind even if backend workers remain healthy.

## Monitoring freshness

- Tightens the existing policy-driven live-now gate for 15-minute monitoring channels.
- Rejects first operational reports such as explosions just heard, smoke currently visible, current fire, preliminary impact reports, responders still working on an unfolding scene, air-raid alerts/clear notices, threats and target movement.
- Removes the previous blanket exemption for generic "attack aftermath" wording.
- Allows settled aftermath only when the report contains stable results, for example confirmed damage/casualties or completed fire/liquidation summaries.
- The behavior remains channel-policy driven and does not hardcode a channel name or ID.

## Telegram source media

- Restores bounded adjacent media stitching for Telegram sources that publish media and text as two consecutive messages.
- Stitching requires consecutive message IDs and the existing five-minute adjacency window; no media is borrowed across another text-bearing post.
- The existing source checkbox `Брати з цього джерела тільки текст (очищати посилання в тілі)` now also suppresses that source's media, matching its visible text-only meaning; the canonical footer/source URL remains.
- Existing source configuration remains compatible; no source names are hardcoded.

## Preserved RC96 behavior

RC97 preserves polling, workers, AI routing, credentials, dedupe, anti-slop, learning, publishing transport, signed updater and migration behavior except for the explicitly listed monitoring/source-media corrections above.
