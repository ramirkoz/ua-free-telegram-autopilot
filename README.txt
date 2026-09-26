UA FREE Telegram Autopilot v2.0.0-rc90 — SIGNED UPDATE CANDIDATE

RC90 is the live-hardening release after RC89 validation.

- Recovers missing Gemini/NVIDIA/Groq/Cloudflare/Local and service credentials even when Codex is already configured; current non-empty values always win.
- First-run import merges encrypted credentials field-by-field instead of blindly overwriting the new portable's current secret pair.
- Repairs carried-forward 5-minute polling to the 15-minute baseline only after real channel rows exist; later operator edits remain authoritative.
- Aligns source and portable Codex dependency on openai-codex 0.156.1.
- Preserves anti-slop, source-specific text-only cleanup, semantic/event dedupe, incident clustering, editorial learning, exact-post Telegram media ownership and signed updater.
