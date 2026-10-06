# UA FREE Telegram Autopilot 2.0.0-rc109

Roadmap release: AI routing / cost optimization + provider discovery.

## Purpose-aware routing
- AI route order now depends on task purpose instead of using one static model order for every call.
- Writer/content tasks prefer Nemotron Super and other cheaper reviewed routes before Nemotron Ultra.
- Short structured JSON tasks prefer Gemini / Qwen / Super before Ultra.
- Explicitly complex tasks may escalate to Ultra earlier, but still only after Super.
- Existing provider health, model cooldown, bounded fallback and QA contracts remain authoritative.
- New routing changes order only; it does not silently enable any new remote provider.

## Cost telemetry
- AI usage telemetry now includes cost/token breakdown by task purpose.
- Telemetry exposes Ultra reference cost and Ultra share of total reference cost.
- Pricing snapshot is versioned as `rc109-2026-10-06-reference`.
- Reference cost remains an OpenRouter-equivalent planning estimate, not a claim about actual current billing.

## Provider discovery
- Added advisory-only provider/model discovery telemetry.
- No discovered provider/model can auto-enable itself.
- Discovery sources currently include NoPaywall and OpenRouter catalogs as manual watch sources.
- Reflection AI Beam is tracked as a watch candidate only.
- Promotion into production routing requires stable API/model ID, credentials, JSON compliance, factual QA, latency, quota/rate-limit, token usage and cost-per-success validation.

## Preserved contracts
- RC108 global text fallback/media-optional behavior remains unchanged.
- RC107 operator-owned approvals, conservative cluster dedupe and signed updater remain unchanged.
- RC105 delivery journal remains crash-safe.
- Free providers remain preferred where product/channel policy allows.

## Live acceptance focus
1. telemetry reports `version=2.0.0-rc109`;
2. writer/content calls no longer reach Ultra while a cheaper healthy reviewed route succeeds;
3. complex tasks can still escalate to Ultra when required;
4. AI usage telemetry includes `by_purpose`, `ultra_reference_usd` and `ultra_reference_share`;
5. provider_discovery appears with `auto_enable=false`;
6. provider degradation does not create retry storms or blocked jobs;
7. publication/delivery/media/manual-approval behavior shows no regression.
