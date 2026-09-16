# UA FREE Telegram Autopilot v2.0.0-rc46

## Modular AI foundation and real local fallback

RC46 rebuilds the AI routing boundary without removing existing Autopilot functionality. Channels, sources, queue/database state, editorial policies, publisher/media rules, telemetry, Supervisor and the signed updater remain intact.

### Provider transport

- Separates fixed AI API traffic from the SSRF-hardened source crawler network transport.
- Provider HTTP uses an explicit HTTPS host allow-list and the operating-system/environment proxy configuration.
- Distinguishes auth, quota, model, timeout, network, temporary and output/task failures instead of labelling malformed AI output as `NETWORK_DOWN`.
- Uses authenticated completion probes after startup/restart and deliberately ignores stale pre-upgrade model cooldowns during those probes.
- Gemini uses `x-goog-api-key` instead of putting the API key in the URL.
- Groq GPT-OSS requests use bounded reasoning and exclude reasoning from the final response.
- Groq Qwen production slot is updated from `qwen/qwen3.6-27b` to reviewed `qwen/qwen3.8-27b`.
- Groq and Cloudflare short JSON gates request JSON object mode.
- NVIDIA custom `chat_template_kwargs` are sent at the wire payload root with thinking disabled rather than wrapped in an SDK-only `extra_body` field.

### Local AI

- Restores Ollama/llama.cpp as a real full writer/final-edit fallback, not only a short classifier.
- CPU long-form output is bounded to 720 tokens with a compacted 5.6k-character working prompt and a 300-second hard timeout.
- Short editorial gates remain bounded to 120 seconds.
- Local article QA rejection is now a task-quality failure and never becomes a fake network outage.
- A single bounded local repair turn is allowed before the job becomes `QUALITY_RETRY`.
- Local timeout cooldown is capped at minutes rather than the previous 30-minute self-ban.

### Safety and compatibility

- Production model routing stays on an explicit reviewed allow-list.
- Existing provider credentials and settings remain compatible; no secret migration is required.
- No database schema change.
- Remote AgentFeed/remote commands stay disabled; signed updater and one-way telemetry stay unchanged.
- Existing RC45 editorial single-media boundary remains unchanged.

### Regression coverage

- Verifies the local engine is eligible for long-form generation.
- Verifies local CPU budgets/timeouts.
- Verifies provider allow-list transport.
- Verifies reasoning-only/invalid output is not misclassified as network failure.
- Verifies Groq reasoning/JSON request shape and current Qwen model id.
