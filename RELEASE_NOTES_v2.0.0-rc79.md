# UA FREE Telegram Autopilot v2.0.0-rc79

Recovery release for the broken RC78 Windows Portable bootstrap.

- Repairs the portable launcher: clicking UA_FREE_Telegram_Autopilot.exe now executes the V2 main entrypoint.
- Startup failures are written to Data/logs/bootstrap_error.log and shown in a visible dialog when possible.
- Removes the accidental LanguageTool shutdown from the "Заблоковано медіа" queue filter.
- Keeps LanguageTool/JRE/Codex under the portable Tools directory, not Data.
- Codex remains a trusted reserve instead of the first route for every AI task.
- First-run migration copies durable channels, policies, sources, article/history and feedback data, but excludes jobs, provider/source health, cooldowns, audit, cache and Tools.
- Manual-test marker disables auto-update until the build is validated on Windows.
