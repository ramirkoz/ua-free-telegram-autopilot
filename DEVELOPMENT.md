# Development and release policy

## Product boundary

UA FREE Telegram Autopilot is a standalone software product. It has its own repository, portable runtime, `Data`, sources, channel history and release lifecycle. It must not be merged into `ua-free-content-tool`.

Code patterns proven in UA FREE Content Tool may be adapted, but runtime state and repositories remain separate.

## Data compatibility

The working `Data` directory is production state, not a disposable cache. Development builds must preserve it unless a documented additive migration is required.

Before any future schema change:
1. make a backup copy;
2. run SQLite `quick_check`;
3. use additive/idempotent migration only;
4. verify row counts and critical channel/source/history records;
5. on migration failure, fail closed instead of silently replacing the database.

Do not commit or upload `Data`, databases, logs, tokens, `secrets.secure` or `secrets.key` to GitHub.

## AI operations

Long or external AI work must be bounded. Each task needs an output budget, request timeout and an overall task deadline. Quota/429 should suppress that provider for the current task and use cooldown rather than repeatedly hammering the same endpoint.

Installed Ollama is the final local fallback. The application does not install Ollama and does not download models automatically.

## Media policy

A wrong image is worse than no image. Advertising, sponsored/promotional media, generic banners, logos, avatars, tracking assets and unrelated AI-summary graphics are not valid editorial media. `og:image` is only a candidate, not an authority.

Captions may translate or shorten source caption/alt metadata. They may not invent visual facts, numbers or claims.

## GitHub editing policy

Repository source edits use whole-file GitHub Contents operations: fetch the complete file, replace the complete file, one file at a time. Do not use blob/tree/chunk patch workflows for this project.

## RC acceptance

A candidate is not stable merely because CI is green. Promotion to `main` requires:
- automated source/compatibility gates PASS;
- Windows build/runtime checks appropriate to the actual portable packaging;
- live startup using a copy of the real previous `Data`;
- AI Router/Ollama smoke;
- Ukrainian rewrite review;
- real media-selection review on a representative article sample;
- controlled Telegram/Telegraph publication when a release changes publication behavior.

RC9 remains on `develop/rc9-foundation` until the live Windows acceptance passes.
