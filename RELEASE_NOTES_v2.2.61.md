# Autopilot 2.2.61 — recover Design Milk through published syndicated RSS

- **P1 commercial source availability:** exactly one operator-known `Design Milk` RSS entry at `https://design-milk.com/feed/`, if enabled, commercial_editorial and `source_health.last_outcome=HTTP_403`, moves to the publicly indexed `https://feeds.feedburner.com/design-milk`.
- Public evidence 30 Oct 2026: Feeder and Inoreader independently report Design Milk's original FeedBurner syndication as working with frequent posts. **Operator LIVE network availability is not yet verified.** This is a published RSS channel, not an evasion of the original site's access restriction.
- Migration once per exact source identity, with same source ID, all existing articles, Telegram delivery receipts, original priority, enabled state and initialized state. Collision with any operator-added source URL fails closed. No old-message re-ingestion or retroactive Telegram replay.
- Clears only the *old URL's* HTTP403 cooldown to allow new endpoint first natural attempt; preserves source success/failure historical totals; retains other 403 cooldowns.
- CTRL+UA and ГРОМАДИ untouched. Other commercial feeds including Shots/Ad Age/Famous Campaigns left unchanged; no network calls in startup migration.
- Editorial thresholds, reader-first story criterion, media provenance, publication intervals, source roster size, budget caps, provider selection, source-date and restart fence unaffected.
- Acceptance: LIVE v61 with exact Design Milk source first collection showing real items/new items and editorial funnel, while no extra old articles/UNKNOWN replay. A successful CI is not LIVE feed proof.
