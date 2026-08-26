# UA FREE Telegram Autopilot v0.1.0-rc41

RC41 fixes the live editorial-topic skew observed in CTRL+UA while preserving the RC40 writing and factual-safety pipeline.

## Changed
- Reworked rolling topic balance into a broader editorial mix: AI/models/agents, practical open-source tools, robotics/mobility, evidence-based science/health, space, hardware/compute, consumer tech, tech business/platforms and cyber.
- Cybersecurity no longer gets an automatic topic-balance bypass merely because a story contains a CVE or is called critical. Ordinary security advisories are capped like other topics; only genuinely broad emergencies/exceptional events can bypass the mix.
- Tightened short-run repetition: cyber is stopped after one recent cyber slot in the last four posts and after two in the last ten; other categories have category-specific rolling caps.
- AI remains a core CTRL+UA topic and therefore has more room than cyber, while robotics, science, practical tools and consumer tech receive independent editorial slots instead of being collapsed into broad buckets.
- RC37 newsworthiness is preserved, but genuinely useful non-shopping open-source resources, libraries, frameworks, courses and tools can be rescued from an overly literal guide/explainer rejection.
- Shopping guides, deals, coupons and accessory roundups remain rejected.
- Cache marker advanced to `telegram-post-v26` so pending/retry candidates are re-evaluated under RC41.

## Preserved
- RC40 SOURCE → optional RU editorial bridge → fresh Ukrainian author architecture.
- Evidence Pack, Fact Guard, number/year checks, Ukrainian hard gate and media-required publishing.
- RC38 event dedupe.
- RC37 adaptive source backoff.
- Existing SQLite/Data compatibility; no schema migration.

## Source strategy
RC41 does not hard-code or silently rewrite the operator's source database. The recommended source mix is managed through the existing Sources UI so priorities can be tuned live without another program release.

## Upgrade
Unpack RC41 into a fresh folder and copy the complete existing `Data` directory from RC40. Do not overlay runtime files onto the old build.
