# UA FREE Telegram Autopilot v2.0.0-rc102

RC102 implements Editorial Queue Contract v2 plus the first AI-efficiency pass after live RC101 acceptance failed.

- `Відхилити` is terminal and verified durable; rejected rows disappear from the editor queue.
- `Погодити й опублікувати` becomes a real publication action. Human-approved rows remain visible until `PUBLISHED` or until the concrete technical blocker is visible.
- Human publication bypasses scheduling/min-interval and repeated editorial QA, but source/media/Telegram/delivery-integrity checks stay fail-closed.
- Human decisions emit explicit `HUMAN_*` telemetry and Supervisor can raise `APPROVED_NOT_PUBLISHED_<channel>` after five minutes.
- Channel fit + editorial value are combined into one AI selector call for standard and commercial editorial channels.
- Selector/value routing is limited to Gemini/NVIDIA; writer/final-editor routing to Gemini/NVIDIA/Groq, preventing quota-exhausted providers from being walked unnecessarily on every task while preserving fallback.
- RC101 durable rewrite/import/unknown-delivery protections remain intact.
