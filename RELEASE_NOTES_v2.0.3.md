# UA FREE Telegram Autopilot 2.0.3

2.0.3 is a focused stabilization patch on top of 2.0.2.

## FastCompany / page-level video binding
This release carries forward the already verified green fix from the post-merge 2.0.2 branch.

Page-level `og:video` / `twitter:player` is no longer trusted merely because the page metadata matches the article.

Accepted video evidence:
- media structurally inside `<article>` / `<main>`;
- article-bound schema.org `VideoObject`;
- page-level video whose asset URL contains article-specific title/id evidence;
- opaque player URL only when a real poster independently binds the player to the article.

Rejected evidence:
- unrelated autoplay/recommendation/decorative page video;
- hero image reused as fake video-poster proof;
- poster alt text without an actual poster asset.

Regression coverage includes the FastCompany-style case:
`https://www.fastcompany.com/91620091/big-tech-is-cutewashing-its-ai-agents`

## Preserved 2.0.2 contracts
- downward-only AI cascade;
- Content Tool-level task-aware OpenRouter routing;
- 2.0.1 telemetry/source-health/media-loss/feedback fixes;
- semver-aware updater.
