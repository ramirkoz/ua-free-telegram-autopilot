# UA FREE Telegram Autopilot v2.0.0-rc75

- Monitoring/community posts now use dynamic minimum and maximum body length derived from source size. Short notices are no longer padded to the channel default minimum.
- Writer prompt explicitly forbids padding short sources, invented advice/morals, and claims that details or deadlines are unavailable unless the source says so.
- Added deterministic monitoring grounding blockers for invented absence/filler statements and generic advice.
- Added hard Ukrainian grammar blockers for malformed forms and mixed imperative/infinitive constructions observed in production.
- Monitoring posts now require a trusted Codex/Gemini final editorial pass before unattended publication. If the trusted editor is unavailable or rejects the text, the job is deferred instead of publishing the draft.
- Fallback-provider drafts in other modes also require trusted final editing when quality/grammar/style signals are weak.
- Optional local LanguageTool corrections are accepted only when they preserve the candidate content, then the full Fact Guard, grammar, readability and Anti-Slop chain runs again.
- RC74 paragraph, corruption, Anti-Slop and V2 Windows Ctrl+V/right-click fixes are preserved.
- No channel-specific hardcoding was added.
