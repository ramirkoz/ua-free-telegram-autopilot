# UA FREE Telegram Autopilot v2.0.0-rc58

## UA Anti-Slop v1
- Adds a deterministic, dependency-free Ukrainian anti-slop gate to the clean V2 writer/final-editor validation path.
- Removes invisible/bidi formatting junk before publication QA.
- Flags high-signal Ukrainian AI-writing patterns, repeated transitions, templated contrast, promotional puffery, mechanical rhythm and chatbot leftovers.
- Profiles are selected from stored channel behaviour (`news`, `commercial`, `community`), never channel ID/name.
- Existing Fact Guard, Ukrainian language QA and source-context checks remain mandatory.
- No extra external-model review dependency is added; the existing gateway simply retries/repairs candidates that fail the deterministic validator.

## Auto-update hardening
- Drive `update_request*.json` and approved `release_manifest.json` accept UTF-8 with or without BOM (`utf-8-sig`).
- This closes the BOM parsing failure found during the RC57 live rollout while preserving SHA-verified fixed GitHub release URLs, DB backup, health proof and rollback.

RC58 preserves RC57 channel-configurable dedupe/editorial profiles, RC54-RC56 production fixes and all existing Data/DB/history/credentials.
