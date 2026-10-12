# Autopilot 2.1.4 — overnight stability

- Disable low-confidence named-event long-phrase duplicate blocking proven to merge unrelated CTRL+UA news in operator Data(3).zip: Citroen 2CV electric concept vs 3D-printed jet plane (#47513/#41843); Microsoft AI agent history cleanup vs independent Meta compute study (#47514/#41352). Preserve exact URL/hash and stronger event-identity guards.
- Enforce durable next_retry_at for all publisher entry points. A failed media download must not be retried before scheduled backoff, even if ingest refreshes media.
- Add regression tests for these false positives and exact URL duplicate check.
- No automatic replay of past DUPLICATE/REJECT rows; preserve Data, operator channel settings, published ledger, source media integrity.
- CTRL+UA editorial selector remains strict: 34 REJECT decisions in Data(3).zip warrant separate audit and human approval; no silent relaxation of rules in this night build.
- 2.1.5 Agent-Reach X/Reddit viral discovery; 2.1.6 Exa/Source Doctor and robust media download; 2.1.7 authorized social platforms; 2.2.0 editorial quality analytics.
- Native Windows regression, portable artifact hash and live operator QA are required. No claim signed overlay updater works; manual install with rollback.
