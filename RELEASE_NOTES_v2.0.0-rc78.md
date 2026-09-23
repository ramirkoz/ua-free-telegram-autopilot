# UA FREE Telegram Autopilot v2.0.0-rc78

Architecture-cleanup manual-test build based on RC77 behavior.

- Heavy reproducible runtimes moved from `Data` to portable-root `Tools`: LanguageTool, JRE and Codex.
- Codex SDK target updated to `openai-codex==0.156.1`; only the active runtime plus one rollback copy are retained.
- Codex is no longer auto-installed on application bootstrap. It is installed only from the application when needed.
- AI routing no longer spends ChatGPT/Codex quota first for every selector/value call; direct providers run first and Codex is a trusted reserve.
- V2 shutdown explicitly terminates the owned LanguageTool JVM, preventing the old portable directory from remaining locked by `java.exe` after the window closes.
- First launch offers a read-only clean import from an older Autopilot folder/Data. Durable channels, policies, sources, articles/history, feedback and encrypted credentials are migrated; logs, cache, Tools, cooldowns, worker state and old runtime queues are not copied.
- Current V2 paragraph/corruption/Anti-Slop QA from RC74-RC77 is preserved.
- Portable packaging is cleaned: current release documentation only; heavy runtime directories are separated from user Data.
