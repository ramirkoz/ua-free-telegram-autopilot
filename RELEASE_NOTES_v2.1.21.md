# Autopilot v2.1.21 — commercial campaign age and duplication gate

- Operator reported Orange/Scamcophony advertising campaign first published Oct 13 reappeared Oct 16 in ПРОДАНО! under paraphrased text and different imagery.
- On last-mile Telegram publish for channel 2, block articles with a known **source_published_at** older than 48 hours. Unknown/invalid source timestamps do not automatically block: provenance must be factual.
- Cross-source dedupe for the identifiable Orange/Scamcophony creative campaign, including English/Ukrainian aliases in the source text; same brand with a distinct campaign remains eligible. Published prior entries only; no duplicate false positives across channels.
- Keeps hard source-media requirement and terminal failed-media recovery from 2.1.20, 2.1.19 live-threat/fact checks and 2.1.18 independent community newsroom access.
- Regression tests: `tests/test_2121_commercial_freshness_campaign.py` and existing full Windows/Ubuntu suite.
- Known limitations: this release does **not** implement general semantic identity for all brands, fix campaign-matched image relevance, resolve CTRL+UA feedback-category learning or improve slow collectors. Those remain next release candidates, subject to LIVE acceptance.
- Operator acceptance after portable install and Data migration: verify no Orange repeat, no stale source-date stories, no false exclusion of unrelated Orange campaigns, and source-owned media output.
