# Autopilot v2.2.59 — Ukrainian copyediting and source-faithful first lines

## Operator evidence read before this release
- Installed operator 2.2.58 LIVE verified at 2026-10-30 15:25 Kyiv:
  RUNNING 3/3 workers + 3/3 collectors, today's 27 posts (CTRL 7, ПРОДАНО 6,
  ГРОМАДИ 14); queue 0/0; 945 COMMITTED, 1 FAILED, one historical UNKNOWN
  protected. New runtime started 15:22; last post 15:16, so v58's actual
  editorial output had NOT yet been observed when this build was initiated.
- The operator DB mirror taken at 14:55 contains actual posts whose final
  Ukrainian still requires polishing:
  * #86826 CTRL: \`Їх спроектували компанія\`, \`проектування\`, while source
    credits SOM/Beijing Institute; retained persons, buildings and numbers.
  * #86839 ГРОМАДИ: lowercase start \`. причиною\` (source said \`могли\`,
    and the output rightly kept that uncertainty).
  * #86807 ГРОМАДИ: \`Шукають повара в шкільну їдальню\`, source denotes
    a cook position, which can be expressed as \`кухар\`.
  * #86652 old video falsely rewritten as new explosions at 09:29, **BEFORE**
    2.2.55 factual guard was deployed; its signature is already protected by
    the source-final guard and is regression-tested here. Do not claim this
    is proof 2.2.58 bypassed a new guard.

## Changes
- Narrow deterministic Ukrainian copyedits for the exact attested grammar,
  spelling, job term and sentence capitalization. Existing
  \`apply_safe_ukrainian_fixes\` is used by the same writer/QA process.
- A shared source-first editorial polish instruction used within the
  existing writer and final editor calls: strong fact-based opening,
  short paragraphs, no unsourced emotional intensifiers, preserve
  uncertainty and source-owned photo/video context. No invented details.
- Regression tests against real observed excerpts and 2.2.55 hard
  source-fidelity signature. Do not hardcode names or forbid source content.

## Unchanged
- No new AI calls, no new media downloads or transfer, no source bans,
  new schemas, source priorities, scheduler/interval changes or operator
  Data writes. Fact Guard, historic Telegram UNKNOWN protection,
  OpenRouter $3/day and $20/month caps remain intact.

## Gate
GitHub full 4/4 CI matrix + Windows Portable/Defender before operator
install. Natural new posts still require SOURCE → FINAL → Telegram audit.
2.2.58 first-cycle collection remains affected by runtime start freshness
filter; this release does not claim to repair its checkpoint.
