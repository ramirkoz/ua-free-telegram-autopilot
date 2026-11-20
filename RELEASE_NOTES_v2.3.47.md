# UA FREE Telegram Autopilot 2.3.47 — real study findings and clean Telegram text

Date: 2026-11-20. Based on two owner-rejected **actual** «ПРОДАНО!» LIVE 2.3.46 posts verified through READ-ONLY SQLite (database quick_check=ok).

## Confirmed defects

1. **Source result omitted (editorial P0)**: article `107785`, PsyPost's long review of GTA psychology/neuroscience research, Telegram message `1327` on 20 Nov 14:11:42 Kyiv. Original source reports actual outcomes (e.g. 135-person Singapore experiment: no statistically significant overall aggression/empathy difference; and 194-person short-term anger measurement). Published 424-character FINAL gave only "results mixed" and how many students played, **not what the study found**. This is a substantive omission, not a length failure or scientific consensus verdict.
2. **Literal Markdown (typography P1)**: article `107861`, source PsyPost pop-song memory study, Telegram message `1328` on 20 Nov 14:42:22 Kyiv; final contained `*Psychology of Music*`, but Telegram Bot API used plain text and explicit source-link entities without Markdown parsing. Publisher's previous cleanup only removed `**bold title**` as an entire line.

## Changes

- New `v2/study_result_completeness_2347.py`: conservative source-only research-outcome extraction for **long, actual study/review sources** with original measured result sentences; pin early positive and negative outcomes to avoid losing long-term "no significant differences" beneath introductory methods. No network call or fabricated paraphrase.
- Writer and trusted final editor prompts receive source-verbatim findings and direct instruction to report at least one **specific measured result** when describing experiments. Bounded deterministic validator catches methods-only drafts/finals; existing model retries, source fact guard, constraints and safety continue to apply. The same check at READY/prepublish returns incomplete posts for bounded quality rewrite, including legacy READY. A legitimate non-study story, short unverified teaser or research summary not purporting to describe methodology remains eligible.
- New `v2/publication_markup_2347.py` + single shared publisher integration: balanced inline `*Journal*` / `**Journal**` -> `«Journal»`, while preserving existing standalone bold-heading unwrap, unpaired stars, escaped literal stars, list bullets and math multiplication; all text/media captions share this path. Does not set Telegram `parse_mode` or interfere with source URL entities.
- Positive/negative regression tests include exact class of both owner incidents, real-world methodology vs measured outcomes, source-verbatim quotes, safe non-study bypass, idempotent typography, math, literal stars and mixed paragraphs. Full GitHub CI and native Windows release gates are required; no acceptance can be claimed from local samples alone.

## Locked operator boundary

- Upgrade is **not** an automatic overwrite of operator 2.3.46. Never modify/replay earlier Telegram 1327, 1328, Data, SQLite, credentials, logs, delivery ledger or two protected `UNKNOWN` during release production.
- Existing channel publication intervals **30/30/5 min**, OpenRouter caps **$3/day / $20/month**, all sources, media provenance and Content Tool unchanged.
- Official Release must come from merged `main` after GitHub CI **4/4 success** and native Windows/Defender build & ZIP SHA256/CRC checks. Release ZIP contains **no operator Data**. Windows operator installs only into a new folder, migrates durable Data and validates one running process.
- Full end-to-end LIVE editorial acceptance remains operator/owner-reviewed after install; do not mark as fully accepted just because a PR merged.
