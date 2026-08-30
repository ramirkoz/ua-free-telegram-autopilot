# UA FREE Telegram Autopilot v0.1.0-rc56

RC56 fixes the remaining Telegram reaction-refresh hang found during RC55 live testing and removes stale RC52/RC53/RC54 wording from the reaction-learning UI.

## Fixed
- Reaction refresh is now strictly READ-ONLY. It no longer attempts to change the channel's available-reaction policy while reading feedback.
- Telegram MTProto refresh uses async Telethon calls with bounded request timeouts and a 30-second total deadline.
- Message reads are chunked and report progress back to the UI.
- If Telegram does not finish within the deadline, the operation returns a visible error and the UI is unlocked instead of staying forever on `читаю…` / `оновлюю…`.
- Manual refresh after switching channels uses the same bounded runtime for every channel.
- Concurrent reaction refreshes are blocked.
- User-facing reaction-learning instructions are version-neutral; stale RC52/RC53/RC54 labels are removed from the tab and Telegram Analytics dialog.

## Preserved
- Operator-only 👍 / 👎 / 🔥 semantics remain unchanged.
- Telegram Premium combinations remain independent: 👍+🔥 and 👎+🔥 are stored as two signals.
- Existing authorized MTProto StringSession is reused from `Data`.

## Installation
Install into a fresh folder and copy the complete existing `Data` directory. Do not overlay runtime files.
