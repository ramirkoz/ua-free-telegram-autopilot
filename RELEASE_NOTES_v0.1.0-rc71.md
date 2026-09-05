# UA FREE Telegram Autopilot 0.1.0-rc71

RC71 fixes the universal editorial pipeline rather than tuning any named channel.

## What changed

- Channel-fit is now strictly a channel-identity gate. A fit score of 60+ is normalized to `publish`; general human interest is evaluated only by the separate Editorial Value Gate.
- `max_age_hours` is no longer a hard global 24-hour guillotine for editorial selection or READY publication. Source age is supplied to Editorial Value as contextual `why_now` evidence. Unknown dates are not auto-rejected.
- Breaking/news is expected to decay quickly, while campaigns, cases, research, analysis, mechanisms and strong evergreen stories may remain editorially valuable beyond the preferred freshness horizon.
- Missing Telegram-ready media no longer kills an editorial story before channel fit / Editorial Value / writer QA. RC71 first uses RC69 media enrichment and cluster media fallback; the real media requirement is re-checked at READY publication.
- Media from another member of the same deduplicated event cluster may be used when the canonical story has no publishable media.
- Recent RC61 freshness, early-media and contradictory channel-policy rejects are requeued once for RC71 reevaluation.
- Monitoring mode remains separate: no Editorial Value, reaction suppression, topic balance or related-story spacing is introduced.
- No channel names or channel-specific special cases are hard-coded.

## Compatibility

Existing Data is preserved. No destructive migration is performed. RC69 media-first settings and RC70 mixed Ukrainian/Russian input remain available.
