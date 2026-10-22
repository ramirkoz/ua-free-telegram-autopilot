# Autopilot 2.2.21: stop tactical air-weapon routes and ambiguous "Бандероль" rewrite

22 October 2026. Candidate based on operator screenshot, original Telegram source and sanitized live SQLite.

- Operator "ЗАПОРІЖЖЯ | ГРОМАДИ" article #74814 / Telegram #3495 at 16:13:26 Kyiv from https://t.me/zaborzp/155137, original 15:57:28. Source: bare transit of a munition named S8000 "Бандероль". AI first draft and final copy both incorrectly recast it as rerouting postal parcels. Publisher returned COMMITTED despite semantic corruption.
- Root cause: current source-only live-now weapon vocabulary did not contain the named weapon and bare-route patterns missed "повз ... / через ...". Previously available rules already prohibited live operational threat tracking; this closes the specific source wording gap.
- New conservative original-source \`MONITORING_LIVE_MUNITION_ROUTE\` veto for opted-in municipal MONITORING feeds at selection and before Telegram sending, including READY queue from earlier installed versions; also adds S8000/Banderol to weapon vocabulary. Settled verified consequences, logistics/parcels, transport updates and nonmonitoring channels remain eligible.
- Regression from exact #74814 original and published final, plus other moving-weapon notices and negative counterexamples: tests/test_2221_munition_live_route_operator.py.
- No remote Telegram deletion, no rewriting earlier published messages, no user Data, source lists, channel preferences, AI routing, publication cadence, media pipeline or receipt mutations. This is a targeted safety/editorial gate, not a general AI hallucination cure.
- Validate CI, native Windows, official GitHub release SHA256 and then independently observe operator LIVE version after installation.

## Added: same-day «ПРОДАНО!» corrupted multi-story Shots page and unrelated gallery

- Operator #74792, Shots «Question time? We're getting better at getting it wrong», https://shots.net/news/view/question-time-were-getting-better-at-getting-it-wrong, Telegram #624–631 at 16:30:54 Kyiv. Sanitized SQLite source contains FOUR separate card headline + summary pairs about films, Gen Z demographics, IKEA/Skyrim and Nike/Mbappé, but does not contain the named story itself. Media pipeline treated nine related page cards as a gallery and selected eight unrelated images. Published generic generational opinion from the second card, not a single verifiable article.
- Model was paid OpenRouter `openai/gpt-5.6-luna` (article writer), NOT proof that switching to an expensive model can repair polluted page extraction. Source body alignment and media provenance were invalid before any writing.
- Source-owned `source_integrity.multi_story_page_cards_reason` finds a high-confidence multi-card / wrong URL-title combination, rejects before AI for EDITORIAL channels, and rechecks at Telegram prepublish (including old READY rows). A coherent single article and true compilations with accurate declared title are preserved; no blanket ban on essays/marketing insights. Refuse ambiguous mixed pages rather than fabricate one story or attach mixed gallery images.
- Regressions in `tests/test_2221_shots_page_integrity.py`, no user-configured providers, sources, Data, cadence, budgets or earlier receipts changed.
