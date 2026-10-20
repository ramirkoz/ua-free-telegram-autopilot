# UA FREE Telegram Autopilot v2.2.6

## Video source integrity

- Prevents text-only publication of Telegram stories when the *same exact source post* contains a video. Checks the exact Telegram post again before sending a text-only candidate, including channels whose general media policy is `preferred` or `optional`.
- If an uploadable original video is recovered, attaches it to that same article and publishes as video. If the original post clearly contains a video but the file is inaccessible, defers with `TELEGRAM_VIDEO_PENDING` and records a diagnostic. If the exact source cannot be verified, retries the source check instead of silently degrading to text.
- Retains authentic text-only Telegram news, rejects media borrowed from neighbours or wrong-post embeds, and never substitutes a poster screenshot for original video. Existing delivered Telegram messages are not resent automatically.
- LIVE regression context: `https://t.me/zaborzp/154789`, article `67312`, destination message `3181` was incorrectly sent as text only on 2.2.5.

## Runtime diagnostics

- Fixes a false CTRL+UA `STALLED` warning: the final supervisor operational states are recalculated after READY-buffer publication availability is measured. A real blocked/dead worker still raises an incident.
- Adds focused regression coverage for exact Telegram video restoration, missing video, unrelated post and error conditions.

## Safety

- No changes to private Data, channel configuration, delivery ledger, posting cadence, secrets, or auto-updater authentication.
- LIVE operator acceptance remains required after installing this release; GitHub CI and Windows build alone cannot prove real Telegram media fidelity.
