# Autopilot 2.1.5 — editorial quality safety

- Reject unfinished Ukrainian text before publication. Operator Ledger article #47923 showed a cut-off generated draft that survived final QA and reached Telegram.
- Remove unsafe hard-limit truncation at an arbitrary word boundary; retain complete-sentence truncation only, otherwise fail closed and retry through the existing generation QA.
- Regression test exercises complete sentence versus mid-sentence truncation.
- Preserve every channel's source-integrity, monitoring, postfactum, and editorial inclusion/exclusion rules. We do not automatically promote unofficial aggregators to trusted primary sources or replay previously rejected stories.
- Known remaining acceptance issue: operator's Data(4).zip showed 130 monitoring decisions and zero posts after 2.1.4; source officiality/primary attribution and date QA require a separate evidence-based fix. No claim 2.1.5 fully restores monitoring output.
- Keep Data/credentials backups; signed auto-update overlay remains unverified. Native Windows Portable is built and validated by release workflow. Live validation still required.
