# UA FREE Telegram Autopilot v2.0.0-rc74

- UA Anti-Slop preserved in the active V2 pipeline and strengthened with hard blockers for corrupted repeated letters/punctuation.
- Restored the proven readability verifier in V2: long wall-of-text rewrites and overloaded paragraphs are rejected.
- Added hard Ukrainian-language blockers for malformed/Russian forms already observed in production.
- Writer and final-editor prompts require 2–4 short semantic paragraphs for normal-length Telegram posts while genuinely short operational posts may stay compact.
- Restored Windows editing in the active V2 UI: Ctrl+V/C/X/A by physical Win32 keycode under Ukrainian layout, Shift+Insert, and right-click Cut/Copy/Paste/Select All for Entry/Text/Combobox fields.
- Based on the user-tested RC73 media extractor; no channel-specific editorial hardcoding added.
