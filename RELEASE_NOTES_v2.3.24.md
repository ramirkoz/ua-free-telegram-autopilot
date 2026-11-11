# UA FREE Telegram Autopilot v2.3.24 — media provenance and output repair

Candidate emergency hotfix based on operator LIVE v2.3.23, 11.11.2026. All operator Data, account settings, Telegram receipts/UNKNOWN, source history, AI budgets ($3/day, $20/month), and 45/30/5-minute channel intervals are retained.

## Changed

1. Commercial web galleries: empty image captions/alt no longer prove that a photograph belongs to an article. Page-declared assets cannot bypass story-specific semantic evidence. The infamous black gadget image attached to unrelated Creative Bloq article in ПРОДАНО! #934 must fail the story-media gate.
2. A shared site image is excluded when it occurs on at least two different source stories, or was previously published for a different source story, even with resized CDN URLs. Same canonical source is not treated as unrelated.
3. Actual published web-image identities (canonical asset key + binary SHA256) are recorded in an **additive** local SQLite table (`published_web_media_2324`) after confirmed Telegram delivery. Reuse on a different article is blocked before sending. Only actually delivered photos enter that ledger; there is no retroactive Telegram action.
4. Regional news: source-only lost-pet/classified guard covers `пропала`, `зник`, `кіт`, `кішка`, `пес`, rather than only variants of `загубив` / `кот`.
5. Science: AMD and common hardware manufacturer acronyms do not falsely fail the no-jargon checker. Unfamiliar acronyms still need an explanation.
6. Utility schedules: a structured table of confirmed utility outage times is not rejected just because it is not expressed as two complete prose sentences. All existing factual verification remains.

## Acceptance/limitations

- Nine targeted offline regression tests pass in the portable source build. **This does not prove live posting, media extraction success for every source, or correctness of all inherited editorial tests.** Actual Windows runtime must be verified using real operator telemetry after installing a new folder and carrying forward the original Data.
- Honest requirement: if an editorial post requires artwork and no picture is proven to belong to the exact source story, hold it instead of fabricating/borrowing another article's illustration. No artificial post-quantity guarantees.
- Built from the supplied v2.3.23 Windows Portable as a source-patched v2.3.24 candidate. Windows native CI and full upstream 1,450-test suite are **not** independently executed by the packaging environment.
- PR #288 remains open pending owner approval; do not merge automatically.
