# UA FREE Telegram Autopilot v0.1.0-rc11

RC11 is a narrow AI-liveness hotfix built on the RC10 runtime and Data format.

## Fixed

- Production AI Router no longer keeps a provider silently suppressed after a successful diagnostic.
- Saving/replacing AI credentials clears stale router cooldowns immediately.
- Copied RC10 Data gets a one-time stale cooldown reset on first RC11 startup.
- Failed local Ollama/llama.cpp fallback now enters a short 3-minute cooldown instead of blocking every queued article again.
- Successful production calls clear both model-level and provider-level cooldowns.

## Preserved

- Fresh `new` articles still run before `retry` rows.
- Retry backoff/cap unchanged.
- Evidence Pack and Fact Guard unchanged.
- Telegram publication, media fallback, dedupe, source collection and AES-GCM secrets unchanged.
- Existing Data schema is unchanged; copy the whole RC10 `Data` folder into RC11 for live testing.

## Reason for this hotfix

RC10 could show `Автопілот: працює` while all cloud providers remained in persistent cooldown and a failing local fallback was retried for each new article. This produced a growing `new` queue with no Telegram publications.
