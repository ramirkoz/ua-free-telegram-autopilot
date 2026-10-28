# Autopilot 2.2.47.1 - commercial ingestion adapter hotfix

The production wrapper now accepts and forwards the optional RSS freshness predicate introduced in 2.2.47. This fixes a startup regression that affected commercial source collection on 28 October 2026.

New regression coverage exercises the production adapter for RSS, HTML and Telegram. Operator settings, media ownership, Data directory, delivery history, budgets and channel schedules are unchanged.

Acceptance requires CI and Windows Defender success, then a separate operator install and live check. Previously blocked external websites are not affected. Ukrainian copyediting remains a separate open issue.
