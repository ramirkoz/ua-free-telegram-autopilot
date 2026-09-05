# UA FREE Telegram Autopilot 0.1.0-rc70

RC70 corrects the channel-language model introduced in RC69.

## What changed

- Added a universal `Українська / російська → Українська` channel mode.
- One channel may now mix Ukrainian and Russian sources at the same time.
- Source language is checked per material; Ukrainian items are rewritten in Ukrainian and Russian items are translated/rewritten into Ukrainian.
- Existing `EN→UA`, `UA/RU→EN`, `UA→UA` and `RU→UA` modes remain available.
- No channel names or channel-specific exceptions are hard-coded into the runtime.
- Removed the redundant legacy language-direction box from the RC70 channel dialog so only one language selector controls the setting.
- RC69 media-first enrichment, strict channel-identity fit, editorial-value second lane, RC67 non-blocking scheduler and all existing Data compatibility are preserved.

## Data compatibility

No destructive migration is performed. Existing channel settings and Data are preserved. A channel must be switched to `Українська / російська → Українська` only when mixed UA/RU input is desired.
