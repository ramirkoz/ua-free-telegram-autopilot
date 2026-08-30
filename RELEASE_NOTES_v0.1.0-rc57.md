# UA FREE Telegram Autopilot v0.1.0-rc57

RC57 closes the live Telegram-feedback/UI failures found in RC56 and upgrades reaction learning from one operator account to a two-layer newsroom model.

## Editor signal
- Editorial feedback is taken from reactions of all channel administrators that Telegram exposes to the authorized MTProto session.
- Each administrator is an independent vote.
- 👍 = topic approval, 👎 = topic rejection, 🔥 = writing/style approval.
- Premium combinations remain independent: 👍+🔥 and 👎+🔥 are two signals.
- Administrator 👎 may hard-suppress only a very similar story and only temporarily.
- If Telegram does not permit complete admin/reaction identity enumeration, RC57 explicitly marks coverage as partial/operator-only instead of pretending it saw every admin.

## Audience signal
- Aggregate reader reactions, views, forwards and replies are collected separately from editor votes.
- Admin reactions are subtracted from aggregate reaction counts when identity scanning is complete/available.
- Audience performance is normalized by views and against the channel's recent baseline.
- Audience performance can softly raise/lower similar topics and sources, but it can never hard-veto a story and never teaches writing style directly.

## Live reliability fixes
- The RC56 UI queue protocol bug is fixed: refresh callbacks use `MainWindow._post_ui()` and the queue pump is fault-tolerant to malformed legacy items.
- A callback failure can no longer kill the Tk queue permanently.
- Telegram refresh has bounded connection/request timeouts, no hidden writes to Telegram, and a 30-second network deadline.
- SQLite feedback writes use one short transaction with a 2-second busy timeout instead of one connection per post.
- Every refresh logs START/PASS/TIMEOUT/DB_FAIL/FAIL with channel, elapsed time and coverage.
- The reaction-memory tab uses version-neutral instructions and shows separate Editor and Audience columns plus admin-coverage status.

## Installation
Install into a fresh folder and copy the complete existing `Data` directory. Do not overlay runtime files.
