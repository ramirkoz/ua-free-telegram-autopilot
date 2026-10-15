# Autopilot v2.1.16

- **Fixed LIVE incident 2026-10-15 18:03 article #56082:** a short notice on elevating the danger level to red is no longer published as a routine municipal news item. Deterministic rejection of bare live danger-level bulletins runs before the AI selector.
- **AI contradiction fail-closed:** selector `PUBLISH` is overridden if the AI rationale explicitly says `should be rejected` / `must not be published` or unambiguous equivalent in Ukrainian. Recorded source failure: `PUBLISH fit=100` with reason `it should be rejected`.
- Preserve verified consequences, evacuation and practical community decisions as candidates, rather than blanket blocking all safety topics.
- Keep full existing Telegram split text + photo-album stitching; regression tested.
- Do not modify user Data on package extraction; install in separate folder and migrate Data from v2.1.15 after backup.
- Live operator acceptance pending after first deployment.
