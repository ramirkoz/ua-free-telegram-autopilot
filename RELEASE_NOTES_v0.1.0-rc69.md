# UA FREE Telegram Autopilot v0.1.0-rc69

RC69 fixes two live editorial gaps found in RC68: media-first stories could be rejected simply because the article body was short, and the language selector still exposed only the older two-direction model.

## Universal, configuration-driven media-first handling

- No channel name is hard-coded into the engine.
- Every channel now has its own media-first settings:
  - automatic enrichment of short source text, or enrichment disabled;
  - whether title + verified media metadata may be sufficient for editorial evaluation;
  - configurable short-text threshold.
- When a short article has video/image evidence, the runtime first collects verified metadata already present in the article layout: caption, alt text, media context and media type.
- For YouTube/Vimeo embeds it also tries bounded oEmbed metadata such as the real video title/channel/provider.
- Verified media metadata is stored as diagnostics and appended to the source evidence before selector/writer/Fact Guard processing. No visual meaning is invented from an unseen frame.
- Short text alone is no longer a valid reason to reject a media-first candidate when that channel permits media-first evaluation.

## Channel identity before generic interest

- Channel fit is stricter about the *kind* of story required by the channel policy, not just topical keywords.
- A repair/DIY/safety story does not become science/technology editorial content merely because it contains technical vocabulary when the channel policy asks for research, discoveries or new technology.
- The rule is generic and follows each channel's configured policy.

## Universal Editorial Value correction

- RC68's universal value gate keeps its normal safeguards.
- RC69 adds a second universal lane for genuinely novel, high-payoff, highly retellable stories, so a strong creative or human hook is not automatically killed only because it lacks large societal consequences.
- Channel fit still decides whether that kind of story belongs in the specific channel.
- RC68 cached value diagnostics are version-bumped and recalculated under the RC69 contract.

## Four language directions per channel

The channel dialog now exposes:

- English → Ukrainian;
- Ukrainian / Russian → English;
- Ukrainian → Ukrainian;
- Russian → Ukrainian.

The direction belongs to the channel, not to editorial/monitoring mode. Monitoring channels can therefore use Ukrainian → Ukrainian or Russian → Ukrainian while continuing to bypass the interesting/not-interesting gate.

## Monitoring behavior preserved

Monitoring still keeps exclusions, dedupe/merge/update, Fact Guard, structural QA, READY-first scheduling and fast publication, while bypassing editorial-interest scoring, feedback suppression, topic caps and related-story spacing.

## Compatibility

- Existing Data is migrated in place; no destructive reset.
- Existing EN→UA and UA/RU→EN directions remain valid.
- Existing channels default to automatic media enrichment with media-first evaluation enabled; both can be changed in channel settings.
- Google Drive is not synchronized automatically before live acceptance.
