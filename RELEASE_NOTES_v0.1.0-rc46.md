# UA FREE Telegram Autopilot v0.1.0-rc46

RC46 is a throughput recovery release for the RC45 editorial gate. RC45 correctly stopped silently skipping channel balance, but made category classification too strict and too expensive. In a real CTRL+UA run this could leave the channel silent even while the collector and scheduler were healthy.

## Editorial throughput
- Category infrastructure failure is no longer treated as an editorial rejection.
- A classifier outage or invalid provider wrapper becomes a **degraded pass** into the existing factual/newworthiness pipeline rather than a channel-wide publication kill switch.
- An explicit valid `__OTHER__` result still rejects material that is outside the channel profile.
- Weight `0` remains a hard category disable.
- Per-channel weights remain active as editorial targets.

## More tolerant category parsing
- Operator category labels are normalized before validation.
- `&`, `and`, connector punctuation, JSON wrappers and harmless provider label prefixes are treated equivalently when the match is unambiguous.
- A single high-confidence fuzzy match is accepted; ambiguous matches are not guessed.
- Examples such as `Science and Health` now correctly map to `Science & Health`.

## Faster classification
- Category assignment no longer calls local Ollama.
- Classification is cloud-only through the configured Gemini/Groq/NVIDIA/Cloudflare routes.
- Classification has a short shared task budget so one difficult story cannot consume most of the publication cycle.
- The core rewrite pipeline keeps its existing provider routing and local fallback behavior; only cheap category assignment is changed.

## Balance starvation escape
- Topic weights remain rolling targets rather than rigid quotas.
- When a category is temporarily over target, RC46 can still publish it after a prolonged channel silence instead of extending a no-post condition indefinitely.
- Zero-weight categories are never rescued by the starvation escape.

## Diagnostics
- Every RC46 editorial decision logs article ID, category and decision (`pass`, `reject`, `degraded-pass`, `starvation-pass`) with the relevant balance reason.
- This makes a zero-output run diagnosable from one log without reconstructing hidden category decisions.

## Source transport cleanup
- Windows browser fallback profile deletion is now best-effort and retrying.
- A transient Edge/Chrome Crashpad lock (`WinError 145: directory not empty`) can no longer turn an otherwise successful public-source fetch into a collection failure.
- RC44 direct RSS/Atom transport behavior is otherwise preserved.

## Preserved RC45 features
- Per-channel English → Ukrainian and Ukrainian/Russian → English content directions.
- Native English newsroom rewrite for reverse channels.
- Pre-rewrite source-event dedupe plus final semantic dedupe.
- Humanized Ukrainian/English editorial style.
- Multilingual Evidence Pack and Fact Guard.
- Existing channel editorial profiles and manual weights.

## Compatibility
- No destructive SQLite change.
- Existing RC45 `Data` folders remain compatible.
- Existing channel directions, weights, sources, publication history and Telegram credentials are preserved.

## Upgrade
Unpack RC46 into a fresh folder and copy the complete existing `Data` directory. Do not overlay runtime files.
