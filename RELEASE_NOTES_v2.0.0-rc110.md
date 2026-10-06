# UA FREE Telegram Autopilot 2.0.0-rc110

Roadmap release: source reliability / crawler cleanup, plus required live fixes found in RC109 telemetry.

## AI contract stabilization
- NVIDIA, Groq and Cloudflare OpenAI-compatible replies now always return the same six-field gateway contract as Gemini/local/Codex paths.
- Fixes live `not enough values to unpack (expected 6, got 3)` failures in writer/editorial/final-editor routes.
- Token/cost accounting remains attached to the normalized provider reply.

## Human-approved publication priority
- Durable editor approvals remain first in READY ordering.
- Approved backlog now uses a bounded one-minute catch-up publication gap while still respecting the channel publication window.
- This drains multi-day approved queues promptly without dumping all posts in one loop.
- Explicit `Publish now` force behavior remains separate.

## Stale backlog cleanup
- Ghost QUEUED/WAITING/LEASED processing jobs whose articles are already READY/PUBLISHED/REJECT/DUPLICATE are closed automatically.
- The cleanup runs before normal TTL expiry and never touches PENDING work.
- This removes false oldest-due/backlog telemetry caused by jobs that claim_job() can never lease.

## Source reliability / crawler cleanup
- Source health now tracks success/failure totals, zero-result streaks, slow streaks, last item/add counts and richer outcomes.
- Deterministic HTTP 403 sources receive an immediate long cooldown instead of being retried every collection cycle.
- HTTP 429, timeout and network failures use cause-specific adaptive cooldowns.
- Successful but >120s sources are marked SLOW and receive bounded cooldown.
- Repeated empty successful fetches are progressively cooled after four consecutive zero-result cycles.
- Unhealthy sources are deprioritized at scheduling time without mutating operator-configured source priority.
- Supervisor telemetry exposes source-health summary and richer slow-source details.

## Preserved contracts
- RC109 purpose-aware cost routing and provider discovery remain unchanged.
- RC108 media is still globally non-blocking.
- RC107 manual-approval ownership and conservative dedupe remain unchanged.
- RC105 delivery journal remains crash-safe.

## Live acceptance focus
1. telemetry reports `version=2.0.0-rc110`;
2. no new `expected 6, got 3` AI failures occur;
3. human-approved READY backlog drains roughly one item/minute inside the publication window;
4. active/due backlog no longer contains old non-PENDING ghost jobs;
5. 403/429/slow sources enter adaptive cooldown and collector cycle duration improves;
6. source_health telemetry reports cause/streak details;
7. delivery unresolved remains 0 and media/manual-approval behavior does not regress.
