# UA FREE Telegram Autopilot 2.0.0-rc106

Roadmap release: cluster same-event dedupe shadow mode.

## RC106 core
- Adds a persistent, non-blocking `dedupe_shadow_candidates` journal.
- Cross-source near-matches are scored from generic event evidence: concept/salient overlap, entities, actions, quantities/durations/numbers and rare terms.
- Shadow candidates never change article decision/stage and never block publication.
- Telemetry exposes candidate count, confidence groups and top shadow matches for RC107 validation.

## Live fixes carried from RC105 acceptance
- Required-media failures are classified as recoverable/probe/permanent with bounded retry backoff instead of turning every first miss into a permanent READY blocker.
- Supervisor exposes media-recovery classes and attempts.
- Commercial-editorial throughput telemetry categorizes reject causes without silently loosening operator thresholds.
- Delivery telemetry now includes committed_24h, oldest unresolved, retry-recovery approximation and unknown-outcome duplicate-risk blocks.
- AI calls persist provider/model/purpose token usage where the provider returns usage metadata.
- Telemetry includes 24-hour input/output/total token counts and a versioned OpenRouter-equivalent reference-cost estimate.

## Safety
- RC106 shadow dedupe is observation-only. Existing validated dedupe gates stay authoritative.
- No channel-name or channel-ID editorial branch is introduced.
- Commercial profile thresholds are not silently mutated.
