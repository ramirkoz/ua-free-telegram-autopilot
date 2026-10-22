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

## Additional verified same-event cross-source duplicate (18:17 / 18:28)
- Operator screenshot and LIVE 18:31:31 recent_events prove ГРОМАДИ Telegram #3514 (article #75211, Zaporizhzhia OVA https://t.me/zoda_gov_ua/68555, 18:17:33) and Telegram #3515 (article #75338, ЗаБор Запоріжжя https://t.me/zaborzp/155167, 18:28:38) both report the same private-residential strike with two confirmed fatalities. Second report has no material update.
- Separate incoming near-identical pieces were actually rejected at 18:28 as `breaking-incident cluster`, but prepublication published-ledger match for #75338 missed #75211. Specific bug: `incident_guard._is_strike_injury` recognized injury verbs but omitted fatality verbs (загинули/загиблі), while generic fingerprint often returned early when cross-publisher headlines had insufficient shared anchors.
- Extend final delivery published-event guard for fatality terms, and require SAME casualty count + private-residential target + city, within 20 minutes of actual committed publication. Explicit new/updated consequences, changed number, different place/target and posts outside the window remain eligible. This protects old READY pieces as well without enabling broad nonblocking shadow-cluster dedup.
- CI regression `tests/test_2222_published_casualty_dedupe.py` covers exact 18:17/18:28 pairing and separated-event controls. No retroactive deletion or replay of already delivered Telegram messages.
