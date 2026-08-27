# UA FREE Telegram Autopilot v0.1.0-rc47

RC47 is a quality-first editorial release based on the live CTRL+UA run from 27 August 2026. RC46 restored throughput, but its degraded category pass could publish off-profile material and its source-only bridge fallback could still produce technically valid but editorially weak posts.

## Editorial selection: no implicit approval
- `__UNCLASSIFIED__` is no longer a publication pass.
- RC47 retries an unavailable/invalid cheap category classifier through a trusted Codex/Gemini assignment-editor pass.
- If classification still cannot be established, the article is held for the normal service retry instead of being published unclassified.
- Cheap lexical category matches are also confirmed by the trusted assignment editor because keyword overlap alone does not prove that a story fits the channel profile.
- Explicit `__OTHER__` remains an editorial rejection and zero-weight categories remain disabled.

## RU bridge: quality over throughput
- Local Ollama is excluded from the RC47 Russian editorial bridge path after the live run showed long bridge timeouts without useful recovery.
- The old `bridge=bypass/source-only` publication path is disabled. If the editorial bridge is unavailable, the article waits for retry instead of going straight from source to publication.
- Fact Guard, number/year checks, media handling, deduplication and provider fallback remain intact.

## Final newsroom pass
- Every English → Ukrainian publish candidate gets a final trusted Codex/Gemini newsroom edit before Telegram publication.
- The final editor may rebuild a weak angle from the source evidence, but the SOURCE EVIDENCE PACK remains the only factual authority.
- Posts must be self-contained: if they mention a loophole, vulnerability, exception, rule change or mechanism, they must explain what it actually is rather than tease a missing payload.
- Corporate announcements are reduced to the concrete change and scale instead of PR framing.
- Technical stories must explain or omit unnecessary jargon for a smart general reader.
- The editor is instructed to select a small number of decisive facts rather than dump every quarterly number or specification.

## Deterministic editorial blockers
- Rejects clipped/lowercase starts that indicate corrupted text.
- Rejects article/author/outlet meta-framing instead of the event itself.
- Rejects stock teaser constructions such as `є лазівка` / `є нюанс` that survived without direct explanation.
- Rejects the observed corrupted phrase `у новій хваті`.
- Rejects media posts overloaded with seven or more numeric tokens, forcing a real editorial selection of facts.

## Cache and compatibility
- Rewrite format marker advances to `telegram-post-v29` so old RC46 publish-ready text is not reused as an RC47 result.
- No destructive SQLite migration.
- Existing RC46 `Data` folders, channel profiles, editorial weights, sources, Telegram credentials and publication history remain compatible.

## Upgrade
Unpack RC47 into a fresh folder and copy the complete existing `Data` directory. Do not overlay runtime files.
