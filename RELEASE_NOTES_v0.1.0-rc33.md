# UA FREE Telegram Autopilot v0.1.0-rc33

## CTRL+UA editorial policy

- Added a pre-AI CTRL+UA audience/newsworthiness gate for zoomers, IT/tech and corporate readers.
- Direct Reddit pages, CAPTCHA/security pages, promo/deal/how-to material, low-value entertainment and cute/pet filler are blocked before expensive rewrite calls unless there is a real research/technology angle.
- Added a hard final blocker for AI refusal/meta text such as “not enough verified facts”, so editorial refusals can no longer receive a high style score and publish.
- Strengthened event-level cross-source deduplication before rewrite and again before Telegram publication.

## Sources

- Source editor now requires Name, URL and numeric Priority 1–100 (100 is highest).
- Existing databases migrate safely with priority 50 for old sources.
- Higher-priority sources are polled first and their fresh stories are processed first.

## Telegram media format

- Photo/video is rendered before the caption text.
- Successfully embedded video no longer repeats its external video link in the caption.
- When video cannot be embedded, the validated image/text fallback retains the video link at the end of the post.
- Source label remains clickable when the fallback video link follows it.

## Compatibility

- RC32 core pipeline is preserved; RC33 policy is installed as a compatibility layer at startup.
- Cached RC32 rewrites are invalidated through a new post-format marker so they pass the RC33 editorial gate before publication.
