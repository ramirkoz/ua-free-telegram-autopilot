# UA FREE Telegram Autopilot v0.1.0-rc79

RC79 stabilizes the three-channel runtime around the actual failures observed in production.

## Telegram monitoring

- Public Telegram collection now preserves native forwarded-message metadata.
- Monitoring can reject native forwards deterministically when the channel's saved exclusion rules forbid reposts/forwards.
- Text-only Telegram messages are briefly held so an immediately following photo or album can be attached to the same logical post.
- Media-first followed by text is also stitched into one logical post.
- Multiple attached Telegram media items are preserved as one donor media package instead of silently collapsing to one image.
- Exact donor Telegram albums can be published as Telegram media groups.
- `required`, `preferred`, and `optional` media behavior is read from the saved channel policy. No channel name selects media behavior.
- Obvious monitoring exclusions configured by the operator can be applied locally before the AI monitoring gate: native forwards, minute-of-silence posts, air-alert/clear messages, protocol greetings and mood-only posts.
- AI monitoring remains for ambiguous inclusion/exclusion decisions; deterministic configured exclusions do not fail open.

## Practical facts

- The writer receives a protected actionable-facts block extracted from source evidence: phone numbers, URLs, email addresses and practical address/schedule/registration lines.
- When a channel's saved writing policy requires preservation of contacts and practical details, the writer is explicitly instructed not to omit or truncate them.

## Editorial value

- Channel Fit still decides whether a story type belongs to a specific editorial channel.
- After a strong Channel Fit, Editorial Value can now pass through one of several universal value shapes: strong mechanism, strong insight, or strong novel/retellable execution.
- This removes the old implicit requirement that every worthwhile editorial story must also have large societal stakes. No channel name is hard-coded.

## Dedupe and sources

- A safer local event-anchor guard separates `same topic` from `same concrete event` when strong version/product anchors differ.
- Multiple publication sources are rendered as compact clickable `Джерело 1 · Джерело 2 · ...` labels instead of raw URLs consuming the post.

## Compatibility

- No destructive database reset.
- Existing channels, sources, tokens, history, reactions, queue and saved channel policies remain compatible.
- RC62/63/64 remain retired from the active runtime.
