# UA FREE Telegram Autopilot 0.1.0-rc35

## Source access and validation hotfix

RC35 fixes the source-onboarding failure exposed by Reuters Technology and, more importantly, stops treating an uncollectable publisher as if it were a usable source.

### Fixed

- HTTP 401 is handled in the same access-control path as HTTP 403/429 instead of falling through as an unexplained source-check failure.
- One bounded navigation-style retry is allowed for public editorial pages.
- After an access block, source detection tries a small bounded set of conventional public RSS/Atom fallbacks.
- Runtime page collection also invokes RSS/Atom fallback for HTTP 401, not only 403/429.
- If neither the page nor a public feed is collectable, the source is not saved as a fake active source. The UI shows a clear Ukrainian warning instead.
- Reuters Technology is explicitly rejected because live Windows validation confirmed `reuters.com/technology/` returns HTTP 401 and no usable public Reuters RSS/Atom fallback is available to this product. Reuters is removed from the CTRL+UA recommended source set.
- Feed fallback probing is bounded to four candidates with short timeouts so a blocked publisher cannot freeze the Add Source dialog for minutes.
- Regression tests cover HTTP 401 retry, feed fallback, Reuters rejection and blocked-source no-save behavior.
- CI includes a real Windows live collection gate on a supported technology-news source so a release cannot pass solely on mocked network tests.

### Preserved

All RC34 functionality remains intact: native Windows launcher and smoke-test release gate, RC33 CTRL+UA editorial policy, source priority 1-100, event dedupe, media-first Telegram formatting, source database migration and AI routing behavior.
