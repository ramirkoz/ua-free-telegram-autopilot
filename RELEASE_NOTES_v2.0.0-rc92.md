# UA FREE Telegram Autopilot v2.0.0-rc92

Emergency live crash fix after RC91 Windows validation.

## Fixed

- Prevented concurrent first-load of the optional Codex SDK from multiple runtime/channel worker threads.
- Codex SDK is now prewarmed once, synchronously, before RuntimeEngine worker fan-out.
- The prewarm is import-only: it does not authenticate, start a Codex subprocess, or make a network request.
- Added a regression that starts eight concurrent callers and verifies the heavy first import occurs exactly once.

## Live failure addressed

RC91 could open the main window, load the migrated V2 database, show all channels/settings/sources, start the runtime, and then terminate with Windows fatal exception `0x80000003` while multiple workers raced through the first `openai_codex` / Pydantic import.

RC92 specifically hardens that startup path. No migration, channel policy, anti-slop, dedupe, editorial-learning, media, or source-selection behavior is redesigned in this candidate.
