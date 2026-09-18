# UA FREE Telegram Autopilot v2.0.0-rc51

## UI freeze hotfix

RC51 targets the remaining Windows GUI stalls seen on RC50 while keeping the runtime/backend path unchanged.

- Keeps all storage/provider reads outside the Tk main thread.
- Applies queue/history/AI Treeview updates in small batches instead of deleting and reinserting hundreds of rows in one uninterrupted Tk call burst.
- Processes only one completed background view per UI pump so several finished refreshes cannot monopolise the Windows message loop at once.
- Preserves unchanged-view suppression introduced in RC50.
- Reduces automatic refresh frequency for heavy operational tables while preserving immediate manual refreshes and tab activation refreshes.
- Preserves row identity and selection where possible and removes stale rows incrementally.
- Cancels pending RC51 render callbacks cleanly during application shutdown.
- Keeps Data, database schema, workers, collectors, provider routing, Supervisor and signed updater compatible with RC50.

The runtime engine is deliberately not changed in this hotfix: the production defect is UI responsiveness, while workers/collectors continued operating during the observed stall.
