# UA FREE Telegram Autopilot v0.1.0-rc51

## Reaction-driven editorial learning
- Manual editorial topic categories and percentage weights are retired from publication decisions.
- Each Telegram channel learns independently from exactly three reactions: 👍 = positive, 🔥 = strong positive, 👎 = temporary negative.
- No reaction is neutral and never counts as a dislike.
- Feedback is dynamic: influence decays with time and expires from selection after 7 days.
- A fresh 👎 can temporarily suppress only genuinely similar material; broad subjects are not permanently banned.
- Positive affinity reorders fresh pending material so stories similar to 👍/🔥 posts are considered earlier while neutral/new subjects remain eligible for exploration.

## Telegram-native writing
- Positive reacted posts become style/angle references for the Ukrainian writer; negative examples are explicitly marked as patterns not to imitate.
- The writer prompt now treats the output as a Telegram post rather than a short website article: concrete first sentence, shorter natural paragraphs, no generic market-summary conclusion and no repetitive canned framing.
- Facts still come only from the current SOURCE Evidence Pack. Reaction memory can influence topic/angle/style but never supply facts.

## Telegram Analytics
- Existing MTProto user-session is reused; no new credentials are required.
- RC51 reads 👍 / 👎 / 🔥 counts separately instead of one aggregate reaction total.
- When the connected Telegram account has sufficient channel permissions, Autopilot best-effort restricts the available channel reactions to 👍 / 👎 / 🔥. Failure to change that optional channel setting never blocks reading feedback or publishing.

## History and compatibility
- Operational/history UI is limited to the latest 7 days. Older published article rows remain internally available for duplicate protection.
- Audit and feedback operational data is pruned on the rolling retention window.
- Existing channels, sources, Telegram bot tokens, MTProto credentials and published history remain compatible.
- RC50 media-required behavior and LanguageTool fix are preserved.

## Upgrade
Unpack RC51 into a fresh folder and copy the complete existing `Data` directory from RC50. Do not overlay runtime files.