# Autopilot 2.2.5 — P0 publication safety Windows Portable

Based on 2.2.4 monitoring event types.

- Block internal AI rejection messages at Telegram publication boundary on all channels. Error/event: AI_REJECTION_LEAK_BLOCKED.
- Correct false geographic off-topic selector rejection only when Zaporizhzhia region and concrete casualty/damage facts are explicitly present in the source. Existing monitoring safety exclusions still apply.
- Add operator incident regression tests.

Operator acceptance pending. Keep a backup of Data; never overwrite the running installation or secrets. Install into a fresh directory and migrate Data only after stopping the old process.
