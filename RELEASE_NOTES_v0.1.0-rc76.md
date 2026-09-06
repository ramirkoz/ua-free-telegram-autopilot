# UA FREE Telegram Autopilot v0.1.0-rc76

## Editorial category weights finally persist

RC76 fixes the real persistence defect exposed after RC75.

- Removes the obsolete RC51 database migration that cleared every non-empty `editorial_weights_json` on startup.
- Removes the obsolete RC51 `set_channel_editorial_weights()` override that discarded the operator's values and wrote `[]`.
- Removes the obsolete RC51 runtime overrides that replaced RC42/RC45/RC46 category parsing with `lambda: []`.
- Reaction feedback and editorial category balance are now independent mechanisms.
- Per-channel category names and weights remain operator-owned settings; no channel identity is hard-coded.
- Adds an integration regression test that writes weights to SQLite, reopens the database, and verifies they survive RC51 installation.

## Compatibility

- Existing `Data` folders remain compatible.
- No reset or destructive migration is performed.
- Channels, sources, tokens, history, reactions and queued state are preserved.
