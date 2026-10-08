# UA FREE Telegram Autopilot v2.0.4

## Codex quota and recovery
- Parse human-readable reset dates, ISO-8601 reset timestamps and relative `try again in` / `retry after` durations from Codex errors.
- Respect the provider-supplied cooldown instead of imposing an unrelated six-hour floor.
- Reconsider Codex automatically on subsequent AI jobs after cooldown expiration, without a runtime restart. When no reset time is provided, retry after a conservative one-hour cooldown.
- Preserve downward-only routing in Codex mode: Codex → OpenRouter → configured free providers.

## OpenRouter compatibility
- Exclude batch-only model IDs ending in `:batch`, which cannot be used at the `chat/completions` endpoint.
- Apply this filter to live catalog, local cache and manually configured model selections.
- Keep task-aware writing and final-editor quality routing with existing budget limits.

## Verification
- Regression tests: Codex relative and absolute reset times, legacy reset message and OpenRouter model compatibility.
- Cross-platform CI: Ubuntu Python 3.12 and Windows Python 3.11/3.12/3.13.
- Live acceptance is required after installing the Windows Portable package.
