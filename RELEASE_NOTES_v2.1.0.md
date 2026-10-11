# UA FREE Telegram Autopilot v2.1.0 — Editorial safety-first

Post-audit stabilization based on 127 posts published under 2.0.11.1 and operator editorial feedback.

Implemented:
- Monitoring selector rejects insufficient/unresolved context (no more doubt -> publish) and has a deterministic pre-AI stop for one-word or ambiguous messages, live threat alerts, raw fragments such as "КАБи", "Ще", "Гучно", "Молнія". Verified official settled notices remain eligible.
- Final Telegram gate rejects leaked AI/meta text (e.g. "Готовий текст поста", "Джерело додасть footer", source refusals) and persists a terminal rejection, never silently re-queues it to another AI for publication.
- Editorial channel significance screening strengthens rejection of garage/hobby demos and minor fan ports, demands evidence for commercial-value claims, and requests 2–3 coherent Ukrainian paragraphs where source material supports that length.
- Web media validator no longer trusts OG image as article hero by default. It excludes URLs reused across distinct articles by the same source and validates media semantic relevance against source text, not AI-generated final text. Five-story shared-ad synthetic regression.
- Event dedupe now recognizes strongly named, rare-term same-event retellings and repeated dated public decisions across different sources.
- Added regression tests for historical editorial failures, official control examples, five independent story images vs shared house ad, same/different-city mourning events.

Preserved: prior 2.0.11.1 Unicode URL hotfix, history, SQLite data, channel configuration, unknown Telegram delivery quarantine, provider settings. No queue reset.

Release acceptance is **not a mere CI green check**: after full Windows Portable, operator must check real CTRL+UA & ПРОДАНО! media from Tom's Hardware, editorial sampling, 100 historic community posts/allowed official notices, semantic duplicates and real publisher telemetry. Synthetic fixture success is not proof that every real site is fixed.

Roadmap source of truth: ramirkoz/ProductVault / 01_PRODUCT/ROADMAP.md, 2026-10-11 operator-approved 2.1.0 editorial-first revision.
