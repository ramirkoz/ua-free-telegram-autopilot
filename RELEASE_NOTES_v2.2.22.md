# Autopilot 2.2.22 — source-owned hearsay rejection

22 October 2026. Based on actual operator LIVE 2.2.21 and a screenshot of a leaked Telegram publication.

## Incident / confirmed defect
- Channel ЗАПОРІЖЖЯ | ГРОМАДИ; article #74908; original source: https://t.me/zaborzp/155159; Telegram #3511, published at 17:47:01 Kyiv.
- Source reported “Світло зникло на Осипку, повідомляють підписники”; an anonymous/subscriber report, not an independently verified utility bulletin. Writer (OpenRouter x-ai/grok-4.20) preserved it in published text.
- Existing original-source regexp covered “підписники повідомляють” but missed “повідомляють підписники”; outage regexp covered “зникло світло” but missed “світло зникло”. No writer or selector score may override this provenance rule.

## Repair / boundaries
- Expand deterministic subscriber, reader, witness, neighbor and chat hearsay matching, including reverse word order, checking both original TITLE and raw_text. Expand unverified power outage phrasing; detect official power utility names with prefixes, e.g. “Запоріжжяобленерго”. Do not treat an unqualified “читачі підтвердили” as independent verification.
- Hard gate in PUBLIC EditorialEngine.select before calling AI (important because LIVE may wrap inner selectors), plus existing hard_editorial_reject / prepublish_quality_issues protects older READY articles immediately before Telegram send.
- Regression tests/test_2222_anonymous_outage_operator.py: exact original source; select/prepublish; unverified paraphrases; institutional positive controls; editorial channels unaffected. Tests run on CI and native Windows before official release.
- Preserve operator Data, source selections, AI provider routing/budgets, intervals, media, receipts, the quarantined UNKNOWN #66297 and previously published Telegram posts. No silent operator setting or remote runtime change.
- Code candidate != user-installed 2.2.22 until manual installation and outbound LIVE telemetry prove version and a real publishing session.
