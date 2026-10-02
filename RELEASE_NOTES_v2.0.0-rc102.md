# UA FREE Telegram Autopilot 2.0.0-rc102

RC102 combines the live editorial-queue repair with the planned AI workload reduction.

- Approved or edited materials stay visible in the editorial queue until they are actually PUBLISHED or explicitly rejected by the editor.
- Human reject is terminal: the job is closed and media/startup recovery paths may not resurrect the article.
- Manual “Publish now” bypasses schedule/min-interval timing, while retaining delivery integrity, exact-published duplicate protection, source/text validity and configured media requirements.
- Human-approved text bypasses automatic editorial pre-publish QA. Technical delivery blockers remain visible instead of silently removing the item from review.
- Adds explicit HUMAN_APPROVE, HUMAN_REJECT, HUMAN_PUBLISH_BLOCKED, HUMAN_PUBLISH_SUCCESS and HUMAN_APPROVE_OVERRIDE telemetry.
- Supervisor exposes human-approved pending rows and raises APPROVED_NOT_PUBLISHED after five minutes.
- Editorial channel-fit and editorial-value evaluation are merged into one structured AI call instead of two separate calls.
- The combined editorial selector skips slow local-CPU fallback; clear reject decisions do not require the full value-metrics payload.
