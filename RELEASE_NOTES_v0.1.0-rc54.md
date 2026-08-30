# UA FREE Telegram Autopilot v0.1.0-rc54

RC54 is the P0 MTProto authorization/reaction-reading hotfix for RC53.

## Fixed
- Telegram authorization now uses Telethon's synchronous facade correctly.
- MTProto runs in worker threads with an explicit asyncio loop on Python 3.11+.
- The UI immediately shows «Підключаюсь до Telegram…», then safely opens the code and 2FA dialogs on the Tkinter main thread.
- Authorization refuses to save an unauthorised or empty StringSession.
- The same fix is applied to automatic/manual reaction refresh, not only to the login button.
- RC54 reaction refresh explicitly uses operator-only reaction labels from RC53, preserving Premium combinations such as 👍+🔥 and 👎+🔥.

## Preserved
All RC53 production-hardening behavior remains unchanged: freshness, canonical dedupe, editorial vetoes, trusted AI routing, semantic QA and existing Data compatibility.

## Installation
Install into a fresh folder and copy the complete existing `Data` directory. Do not overlay runtime files.
