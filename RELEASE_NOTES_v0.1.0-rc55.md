# UA FREE Telegram Autopilot v0.1.0-rc55

RC55 fixes the reaction-refresh lifecycle bug found immediately after RC54 live testing.

## Fixed
- The first reaction refresh after Telegram authorization and later manual refreshes now use the same RC54 MTProto transport.
- Switching from one channel to another no longer falls back to the stale RC51 Telethon function imported by the UI before RC54 was installed.
- `Оновити реакції зараз` is rebound directly to the RC54 sync MTProto reader.
- Unexpected refresh exceptions are converted into a visible Telegram Analytics error instead of leaving the UI stuck forever on `читаю…` / `оновлюю…`.
- A refresh in-flight guard prevents two Telegram reaction readers from being started simultaneously.

## Preserved
All RC54 authorization/session handling and RC53 editorial-learning semantics remain unchanged, including operator-only 👍 / 👎 / 🔥 and Premium combinations.

## Installation
Install into a fresh folder and copy the complete existing `Data` directory. Do not overlay runtime files.
