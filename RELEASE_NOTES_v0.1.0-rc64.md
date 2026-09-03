# UA FREE Telegram Autopilot v0.1.0-rc64

RC64 is a live-training tuning release based on the RC63 production logs and published posts.

## What changed

- **Throughput:** RC63's 60-minute CTRL+UA / 90-minute ПРОДАНО! editorial spacing is removed. Only a 5-minute technical anti-double-send delay remains; quiet hours 00:00–07:00 are preserved.
- **No hard saturation quotas:** repeated sources/topics are softly deprioritized instead of being hidden. Good candidates remain eligible.
- **ПРОДАНО! scope:** the selector now explicitly treats consumer behavior, pricing, retail/e-commerce, dark patterns, loyalty, packaging, platform monetization, creator economy, influencer mechanics, viral products, PR fails and behavioral experiments as first-class stories, not just campaign case studies.
- **Human-interest quality remains strict:** RC64 does not revert to an ad-industry digest. It adds a separate behavioral/commercial pass route for non-campaign stories with a strong broad-reader hook.
- **Selector observability:** PASS/REJECT logs now include fit, human-interest, friend-share, creative-surprise and marketing-mechanic scores plus the reason.
- **Natural Ukrainian names:** writer instructions require Ukrainian forms for people and established common names while preserving brands/products/models/formulas. A targeted fallback localization pass runs only when clearly localizable Latin names remain.
- **Cross-source dedupe:** a 36-hour strong-headline event fingerprint catches differently written reports about the same concrete event, including the Saturn-decagon failure observed in RC63.

## Preserved

- RC63 semantic 👍/👎 learning and 🔥 style-only learning.
- Final Ukrainian QA and factual validation.
- Media-required behavior and source/video footers.
- Existing SQLite `Data`, channels, sources, Telegram credentials and reaction history. No destructive migration or Data reset is required.

## Live acceptance

GitHub CI/release validation is required before distribution. Native live acceptance remains a separate step and must be judged from the operator's real RC64 logs/posts after installation.
