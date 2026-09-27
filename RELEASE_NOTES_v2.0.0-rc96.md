# UA FREE Telegram Autopilot V2 2.0.0-rc96

Windows validation build based on RC95 with a targeted monitoring-channel relevance gate.

## Monitoring channels
- Keeps the 15-minute polling baseline.
- Adds a channel-policy-driven pre-AI rejection gate for minute-lived live-now alerts that are already stale by the next collection cycle.
- Rejects air-raid alert/clear notices, immediate threat notices, current UAV/rocket/Shahed/air-target movement or direction, including euphemisms such as “мопед”, and current “зараз палає/горить” or “щойно пролетіло/побачили/зафіксували” reports.
- Keeps durable aftermath and non-live information eligible: “було атаковано”, damage/consequences, openings, construction, found items, decisions, repairs, aid and scheduled future changes such as “завтра змінять маршрут”.
- The rule is stored in the monitoring channel rejection policy and is not hardcoded to a channel name.

## Preserved RC95 behavior
- Channel/source settings, editor queue, media stitching, dedupe, anti-slop, learning and publishing logic remain intact.
- Provider-aware AI routing, credential handling, direct outbound Drive telemetry and signed update mechanisms remain unchanged.

This prerelease is for live Windows validation. User acceptance is not implied by CI or release publication.
