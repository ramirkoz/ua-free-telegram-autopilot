# UA FREE Telegram Autopilot v2.0.0-rc50

## Live hardening: Groq, MEDIA backlog, responsive UI

RC50 addresses three production defects observed overnight on RC49.

- Fixes Groq GPT-OSS requests that sent unsupported `reasoning_effort=none`; GPT-OSS now uses the supported low setting while hidden reasoning remains excluded from output.
- Removes OpenAI-specific reasoning controls from the Groq Qwen fallback so provider validation cannot disable an otherwise usable model.
- Keeps RC49 structured-JSON retry/budget safeguards intact.
- Adds a bounded 30-minute recovery window for READY/PUBLISH rows blocked by required media. A complete recovered bundle is unblocked; a permanently missing/incomplete required bundle is archived instead of remaining an immortal READY blocker.
- Preserves fail-closed required-media policy: RC50 never silently publishes a required-media item as text-only.
- Removes worker-thread Tcl/Tk calls from periodic UI refresh. Background workers now communicate through a thread-safe result queue consumed only by the Tk main thread.
- Skips repainting unchanged views and reduces refresh frequency for heavy queue/history/channel tables.
- Keeps runtime workers, collectors, Supervisor, remote updater, Data and database schema compatible with RC49.
