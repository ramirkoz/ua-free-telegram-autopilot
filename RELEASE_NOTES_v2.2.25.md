# Autopilot 2.2.25: durable delivery-grounded event memory

- Adds channel-scoped persistent event registry and immutable publication snapshots for **COMMITTED** deliveries. Records survive ordinary article retention.
- Searches recent actual PUBLISHED article rows **only** when backed by COMMITTED delivery journal or archived receipt. UNKNOWN, FAILED, READY, models and absent timestamps are never delivery evidence.
- Detects cross-source repeated fatal strike reports versus material confirmed changes to the fatality count using **original source texts**, never AI-written captions. Same-event repeats are marked DUPLICATE; 2→3 confirmed deaths is allowed as an UPDATE and linked to one event ID.
- Conservative 48h window: a precisely matching named street can link reports up to 48h; less-specific same-city/private-home descriptions require a 4h window. Different streets, homes versus apartments, explicitly separate attacks and different channels are not merged.
- Integrated into the actual shared pre-AI and pre-Telegram published-event dedupe, with persisted post-delivery snapshots. Old COMMITTED reports can seed a stable event ID without rewriting historical receipts.
- Scope limitation: newly structured event classification covers identifiable **fatal strike incidents**. Existing semantic/category-specific dedupe remains for other events. This does not prove full claim entailment for all topics.
- Does not change user Data, sources, AI providers, costs, schedules, human-review policy, media, publication journal, or protected UNKNOWN #66297. No automatic replay.
- Release gates are separate: PR 4/4 CI, Windows native GUI/Defender build, official tag & SHA-256, and later operator manual install/LIVE editorial acceptance.
