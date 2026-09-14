# UA FREE Telegram Autopilot v2.0.0-rc27

## Startup stability hotfix

- Fixes the RC26 startup race: Production UI now creates `ProductionSupervisorService` directly and starts one supervisor generation instead of Base -> Advanced -> Production churn.
- Supervisor, agent-feed and update-status writes use collision-free temporary names and bounded retry for transient Windows file locks (`WinError 5/32/33`).
- Google Drive Desktop mirror locks are treated as transport problems and no longer destabilize the local application.
- Existing `Data` remains compatible. `Data\\ai_runtime` is preserved, so an already installed Codex runtime is reused instead of installed again.
- No operational database migration is introduced in RC27.

## Regression coverage

- Production startup path is checked to prevent reintroduction of triple supervisor startup.
- Production supervisor atomic status writes are tested.
- Transient Windows-style lock retry is tested.
