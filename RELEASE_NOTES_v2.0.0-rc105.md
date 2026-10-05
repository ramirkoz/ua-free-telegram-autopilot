# UA FREE Telegram Autopilot 2.0.0-rc105

Roadmap release: durable delivery journal and crash-safe publication outcome.

## Durable delivery journal
- Every Telegram publication now has a persistent SQLite journal state: PREPARED -> SENDING -> ACKNOWLEDGED -> COMMITTED.
- The journal records delivery mode, attempt count, message IDs, media counts and timestamps.
- Telegram acknowledgement is persisted before the article is committed as PUBLISHED.
- If the process restarts after acknowledgement but before the DB publication commit, RC105 recovers the acknowledged result and commits it without sending again.
- If the process dies while a remote send is in-flight and no acknowledgement was durably recorded, RC105 marks DELIVERY_OUTCOME_UNKNOWN and blocks blind retries instead of risking a duplicate Telegram post.
- PUBLISHED article state, DONE job state and delivery-journal COMMITTED state are committed in one SQLite transaction.
- Supervisor telemetry exposes delivery-journal counts and unresolved in-flight/unknown deliveries.

## RC104 acceptance fixes carried into RC105
- Supervisor telemetry exposes a stable six-provider registry: Gemini, NVIDIA, Groq, Cloudflare, Local AI, Codex/ChatGPT.
- Structured editorial tasks get a larger completion ceiling without forcing longer outputs.
- NVIDIA structured tasks request JSON-object output; Gemini JSON tasks use a larger structured-output budget.
- Editorial JSON parsing tolerates fenced JSON, balanced-object extraction, smart quotes, trailing commas and safe Python-dict syntax.
- Existing RC104 Drive telemetry, Shared Drive, editorial-priority, image-normalization and startup/database fixes are preserved.

## Safety contract
RC105 prefers a visible unresolved delivery over a duplicate publication. An UNKNOWN delivery requires operator reconciliation; it is never blindly resent.
