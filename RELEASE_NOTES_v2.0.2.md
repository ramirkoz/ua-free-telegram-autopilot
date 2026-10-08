# UA FREE Telegram Autopilot 2.0.2

2.0.2 corrects AI routing architecture and raises OpenRouter model selection to the Content Tool level.

## AI cascade
The operator selects the highest allowed AI tier:
- Codex / ChatGPT -> OpenRouter -> free providers
- OpenRouter -> free providers
- Free providers -> free providers only

Fallback is strictly downward. Autopilot never escalates upward from OpenRouter to Codex or from free providers to paid/Codex routes.

## OpenRouter task-aware model quality
OpenRouter routing now follows the same quality-tier principles as Content Tool:
- selectors / monitoring / value gates: FAST_CHEAP -> STRONG
- writer / final editor / rewrite: STRONG -> PREMIUM
- fact / quality / research: STRONG -> PREMIUM
- generic tasks: BALANCED -> STRONG

Candidate selection considers:
- task quality tier;
- prompt/output context requirement;
- model quality class;
- blended token price;
- strategy economy/balanced/quality;
- model/provider health and cooldown.

A low-cost quality-2 model such as Mistral Nemo is therefore not an acceptable normal writer route under balanced strategy.

## Operator UI
One canonical AI mode selector replaces overlapping backend toggles. OpenRouter and Codex remain separately configurable/testable, but routing permission is controlled by the cascade selector.

## Preserved 2.0.1 contracts
- telemetry-driven source cooldown / KNOWN_ONLY fixes;
- durable media-loss accounting;
- feedback auto-refresh observability;
- OpenRouter automatic catalog;
- semver-aware updater.
