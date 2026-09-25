UA FREE Telegram Autopilot v2.0.0-rc89 — REMOTE UPDATE CANDIDATE

RC89 is based on RC88.

- Repairs RC88 partial credential migration: when the current Data has no configured AI route, the app validates sibling Autopilot encrypted secret pairs and restores only missing secret fields from the best valid previous Data.
- Existing non-empty current secrets are never overwritten.
- Repairs the carried-forward 5-minute polling regression with one explicit 15-minute migration pass; later operator edits remain authoritative.
- Keeps the RC88 V2 database carry-forward fix.
- Keeps RC86 source text-only cleanup and cross-source duplicate protection.
