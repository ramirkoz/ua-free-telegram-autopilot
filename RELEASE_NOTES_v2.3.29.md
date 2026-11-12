# UA FREE Telegram Autopilot v2.3.29 · CTRL+UA buyer-guide P0 correction

**Release scope:** precise editorial source-only safety fix for [#300](https://github.com/ramirkoz/ua-free-telegram-autopilot/issues/300). Previous 2.3.28 remains LIVE until the operator installs this package.

## Fix
- Reject ordinary retail roundups / buying guides in **CTRL+UA** only when both source title and multiple independent article-body signals confirm shopping content (affiliate commissions, buying ranks, shopping-selection/retailer links).
- Perform this check before paid editorial selection; repeat it at the existing final pre-Telegram hard-stop for previously prepared READY stories. A direct selector caller is protected as well.
- Verified original regression: 12 November 2026 Popular Mechanics “The 6 Best Electric Snowblowers…” article 97242, published erroneously as CTRL+UA Telegram #1857.
- Keep genuine technology breakthroughs, innovative products, new studies, robot inventions and test findings eligible. Do not block all Popular Mechanics or other channels.
- Focused regression tests distinguish shopping lists from research and validate both admission and final publication gates.

## Safety and outstanding items
- Never automatically delete message #1857 or alter historic Telegram deliveries.
- No changes to operator SQLite Data, enabled sources, 45/30/5 intervals, Telegram UNKNOWN receipt isolation, budgets, media, queues or language controls.
- Existing [#299](https://github.com/ramirkoz/ua-free-telegram-autopilot/issues/299) preboot queued-item rejections, ПРОДАНО! throughput, RSS, full 1472-label replay and Naruto media regression remain separate open tasks.
- CI + Windows Portable build + initial LIVE checks required before calling this release production-accepted.
