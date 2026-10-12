# UA FREE Telegram Autopilot 2.1.3

## CTRL+UA: high-precision deduplication hotfix
- Harden cross-source event matching: generic scraped boilerplate and social-sharing footer text cannot mark two unrelated stories identical if their substantive headline anchors do not overlap. Exact URL and exact content-hash duplicate checks remain intact.
- Prevent rejected source articles from being treated as canonical same-event evidence in the fingerprint engine.
- Add regression tests for unrelated Microsoft Maia/OpenAI-model and iPhone accessories/Ugreen-discount examples.
- All original channel settings, operators' Data, provider credentials, existing published ledger and editorial rules are preserved. No automatic replay of historical duplicate decisions; re-review remains a controlled follow-up after the quality gate.
- GitHub PR #171 merged. New 2.1.3 public/package/runtime version and native Windows CI required.
- Live acceptance: CTRL+UA publishes fresh, verified new events and keeps actual repeats blocked, with no stale-post flood.

## Later work
- 2.1.4: operator-controlled X/Reddit discovery and viral-topic radar.
- 2.1.5: Exa / Source Doctor / media retry backoff.
- 2.1.6: authorized additional social adapters.
- Content Tool RC60 is unchanged.
- Signed auto-update overlay unverified; manual Portable install and preservation of Data required.
