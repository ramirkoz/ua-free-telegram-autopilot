# UA FREE Telegram Autopilot v2.0.0-rc42

## Throughput recovery for CPU-only notebooks

RC42 targets the backlog observed during the RC39/RC41 overnight run on a 24 GB RAM notebook without a discrete GPU.

- Ollama/local AI is now a short-task fallback only. Long-form writer/final-edit generations no longer route to the CPU model.
- Short local editorial gates use a compact context, at most 220 output tokens and a 120 second execution ceiling.
- Repeated malformed local answers trigger a 30 minute model cooldown instead of repeatedly burning several minutes of CPU time.
- Local timeouts trigger a 30 minute cooldown; repeated transient network/model failures get exponential cooldowns.
- Editorial fit/value prompts were reduced for the CPU fallback while cloud writer quality rules remain unchanged.
- Sources that repeatedly take 120+ seconds to fetch are treated as degraded and enter the existing source cooldown path.
- Local Telegram operational reports now include due backlog, oldest due age, jobs completed in 30 minutes, per-channel due/done/published throughput, provider states and the slowest sources.
- Existing fresh-first queue ordering and hard channel TTL expiry remain intact; no database schema change.
- RC41 local-only Supervisor architecture, remote-agent shutdown, signed self-update, health validation and rollback are unchanged.
