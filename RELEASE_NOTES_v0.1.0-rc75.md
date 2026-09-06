# UA FREE Telegram Autopilot v0.1.0-rc75

## Channel settings are now one loss-resistant transaction

RC75 fixes the misleading nested-save behavior exposed while editing per-channel editorial categories and weights.

- The main channel dialog is the single persistence boundary and its button is explicitly named **«Зберегти канал»**.
- Fine-policy and editorial-weight subdialogs now say **«Застосувати до форми каналу»** instead of pretending that they already persisted the whole channel.
- Adding or editing one editorial category uses **«Додати до списку» / «Застосувати зміну»** so the scope of that action is explicit.
- Closing the main channel dialog with unsaved changes now asks whether to save the whole channel, discard the draft, or return to editing.
- The unsaved-change guard covers ordinary fields plus pending fine policy and editorial category weights.
- The channel window title is taken from the actual package version, so stale hard-coded `RC72/RC73` labels can no longer misidentify the running build.

## Architecture rule preserved

RC75 contains no knowledge of CTRL+UA, ПРОДАНО! or any other channel identity.

Universal mechanisms remain under the hood. Channel-specific language direction, schedules, editorial mission, inclusion/exclusion rules, writing/style rules, examples, prompts, media policy and editorial category weights remain operator-owned settings of that channel.

## Compatibility

- Existing `Data` folders are compatible.
- No destructive migration or reset is performed.
- Existing channels, sources, tokens, history, reactions and queued state are preserved.
