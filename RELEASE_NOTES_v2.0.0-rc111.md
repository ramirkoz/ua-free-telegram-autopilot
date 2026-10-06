# UA FREE Telegram Autopilot 2.0.0-rc111

Roadmap release: QUALITY/retry efficiency + final collector-latency optimization.

## Deterministic local QA repair
- Writer/final-editor candidates are locally normalized before another provider is tried.
- Over-limit Telegram bodies are shortened deterministically at a sentence/word boundary.
- Footer-only source attribution wrappers are removed locally when channel policy forbids source attribution in the body.
- Monitoring URL cleanup remains preserved.
- The local repair layer never invents or silently changes facts/numbers.

## Cross-provider QA fail-fast
- Repeated deterministic QA failures are classified into stable classes such as length, invented_number, source_attribution, structure and JSON.
- If two reviewed routes hit the same deterministic QA class in one gateway cycle, the gateway stops trying a third/fourth model.
- This prevents token burn where every model repeats the same mechanically detectable mistake.
- Provider health remains unaffected by task/output QA failures.

## Bounded QUALITY retry budget
- Article-level QUALITY retries are now bounded.
- Deterministic failures such as invented numbers, hard-length/source-attribution and broken JSON receive one completed retry after the initial attempt.
- Other QUALITY failures receive at most two completed retries after the initial attempt.
- On exhaustion:
  - if a final_text already exists, it is preserved as READY for human review;
  - otherwise the pending article is terminally rejected with QUALITY_RETRY_EXHAUSTED.
- Provider outages remain separate and do not consume the QUALITY retry budget.

## Collector latency / low-yield scheduling
- Source low-yield streak now means "no new article added", even when the source returned already-known items.
- After three consecutive no-add cycles, a source receives bounded cooldown.
- Sources taking >=30s with zero additions are marked SLOW_EMPTY and cooled immediately.
- Existing >=120s SLOW handling remains and gets a wider bounded cooldown.
- Scheduling deprioritizes SLOW_EMPTY together with other unhealthy outcomes without mutating configured source priority.
- This specifically targets live patterns such as 20-40 known items fetched every 15 minutes with zero additions.

## Telemetry
- New top-level quality_efficiency snapshot:
  - quality_retries (last 60m)
  - quality_exhausted (last 60m)
  - quality_active
- Source-health summary now counts SLOW_EMPTY and no-add streak >=3.

## Preserved contracts
- RC110 source-health/backlog/human-approved priority remain unchanged.
- RC109 cost-aware routing/provider discovery remain unchanged.
- RC108 media remains globally non-blocking.
- RC107 editorial-review ownership/dedupe remain unchanged.
- RC105 delivery journal remains crash-safe.

## Live acceptance focus
1. telemetry reports `version=2.0.0-rc111`;
2. repeated hard-length/source-attribution errors no longer fan out across 3-4 providers;
3. quality_efficiency is present and QUALITY active/retry counts trend down;
4. no article loops indefinitely in QUALITY_RETRY;
5. final_text, if present, survives retry exhaustion into human review;
6. repeated no-add/slow-empty web sources enter cooldown and CTRL+UA/ПРОДАНО! collector duration falls materially;
7. delivery unresolved remains 0 and publication/media/manual-approval behavior does not regress.
