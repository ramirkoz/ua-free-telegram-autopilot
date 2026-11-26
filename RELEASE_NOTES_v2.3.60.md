# 2.3.60 — AI cost efficiency
- Combined final editor and reader acceptance; persistent exact source/body/policy receipts; inherited READY still checked.
- Article-scoped paid editorial dispatch limit (5 expensive, 8 total), observed actual spend admission threshold $0.010; no reset on restart, no strict upper bound on a single provider charge. Existing global $3/$20 operator budgets unchanged.
- Distinct reader_gate usage, attributed to article; one paid attempt per invocation.
- Targeted correction never falls back to full selection/writer, at most one reader/polarity rework; fail closed on source QA.
- Prefer lower price within the same quality tier and sufficient context, without modifying manual model order. Remove exact duplicate prompt lines and duplicate monitoring guidance; retain one complete owner-approved style example. No source truncation beyond existing evidence packs.
- Fix joined source sentences and unrelated negation scope; real incident 113881 reproduced and corrected. Actual 114385 final text unavailable; that incident is not claimed reproduced. Genuine aligned polarity flips remain blocked; check at writer/final stage.
- All channel policies, cadence, media ownership and delivery safety retained. Candidate based on official 2.3.59; native Windows CI/actual savings not yet verified.
