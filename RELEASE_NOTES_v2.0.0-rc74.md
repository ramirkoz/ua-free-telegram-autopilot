# UA FREE Telegram Autopilot v2.0.0-rc74

- Restored the full V2 editorial quality chain: UA Anti-Slop remains active and now works together with the proven readability/corruption verifier.
- Blocks long wall-of-text rewrites (350+ chars without paragraph structure).
- Blocks generative corruption such as repeated-letter runs (`пппппп...`) and absurd punctuation runs.
- Adds hard Ukrainian-language blockers for high-confidence malformed/Russian forms observed in production.
- Writer and final-editor prompts now require 2–4 short semantic paragraphs for normal-length Telegram posts while allowing genuinely short operational posts to stay one paragraph.
- Restored Windows editing support in the active V2 UI: Ctrl+V/C/X/A by physical Win32 keycode under Ukrainian layout, Shift+Insert, and right-click Cut/Copy/Paste/Select All for Entry/Text/Combobox fields.
- No channel-specific editorial hardcoding added.
