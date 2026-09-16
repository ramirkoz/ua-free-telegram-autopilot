# UA FREE Telegram Autopilot v2.0.0-rc49

## Groq structured-output recovery and cross-community duplicate guard

RC49 fixes two live production problems observed on RC48: Groq could reject short editorial JSON gates after consuming the completion budget, and the Communities channel could publish the same public-service notice from different municipalities as separate stories.

- Classifies Groq `json_validate_failed` / incomplete structured generation as a task-level validation failure, not as an unsupported/dead model.
- Gives Groq structured editorial gates a bounded realistic completion budget while keeping ordinary requests unchanged.
- Disables Groq reasoning for JSON gates, forces deterministic temperature, and adds a compact JSON-only output contract.
- Performs one bounded same-model structured retry before normal Groq model fallback; persistent format failure falls through to the next AI route without poisoning provider health.
- Extends semantic dedupe with a high-precision cross-community public-service lane for municipal/community reposts that use different local names, photos and rewritten headlines for the same ministry/service announcement.
- Uses normalized Ukrainian concept fingerprints plus body/final-text corroboration, while keeping different services for the same audience separate.
- Keeps the existing pre-publish duplicate gate, so stale READY items are checked against already published stories immediately before Telegram publication.

Existing V2 `Data` remains compatible. No destructive database migration is introduced.
