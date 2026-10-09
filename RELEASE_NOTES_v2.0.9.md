# Autopilot 2.0.9 — editorial model quality floor

## Scope
- Automatic OpenRouter routes for `writer`, `final_editor`, `rewrite`, `complex_rewrite` now require model quality tier >=3 under `economy`, `balanced`, and `quality`. This prevents lower-tier candidates such as Mistral Nemo from authoring text via auto-discovery. The 2.0.8 exclusion of `multi-agent` for editorial auto-discovery remains in force.
- Inexpensive model selection for auxiliary routing (`editorial_selector`, `monitoring_selector`, `health_probe`) remains unchanged; explicit operator-configured models remain under operator control.
- Regression tests added for every editorial purpose and routing strategy.
- The existing 2.0.8 postfactum, grounded-text, media and contact-preservation guards remain unchanged.

## Safety
- No changes to startup, SQLite migration, Data, credentials, channel policy, budgets, Telegram publishing, workers, or Content Tool.
- No new Codex feature; disabled operator mode is respected.
- This is a **narrow initial 2.0.9 safety change**, not proof all editorial, media, backlog and expense issues are solved. Live source-to-post review required before unsupervised night use.
