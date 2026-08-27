# UA FREE Telegram Autopilot v0.1.0-rc48

RC48 adds a per-channel Editorial Learning Loop. The editorial profile, operator-defined weights, current SOURCE evidence and Fact Guard remain authoritative; audience performance is a learning signal, not a replacement editorial policy.

## Telegram performance memory
- Adds optional read-only Telegram analytics through MTProto using a Telegram user session.
- Bot Token publication is unchanged. The user session is used only to read metrics of posts that Autopilot already published.
- Collects available channel-post views, forwards, reactions and replies.
- Stores comparable snapshots at approximately 2, 8, 24, 72 and 168 hours after publication.
- Analytics failures are fail-open for publishing: an unavailable Telegram analytics session never blocks collection, rewriting or Telegram publication.

## Per-channel Editorial Learning Loop
- Every Telegram channel has its own performance history. Metrics or examples from another configured channel are never mixed into its memory.
- The memory activates only after at least 10 posts are available at one comparable checkpoint.
- The preferred comparison window is about 24 hours, with other configured checkpoints used only when they have enough comparable history.
- Autopilot maintains a TOP-30 of successful posts for the selected checkpoint using real audience interactions. No invented editorial percentage score is introduced.
- For a new story, up to four relevant successful posts are selected from that channel's TOP history.

## How memory influences the editor
- Successful examples are supplied as soft editorial context to assignment selection, the Russian editorial bridge and the final Ukrainian newsroom pass.
- Examples may guide story angle, factual density, ordering and presentation style.
- Historical examples are explicitly NOT factual evidence for the current story and must never contribute facts, numbers, dates or claims.
- Channel profile, editorial weights, current SOURCE evidence and Fact Guard always outrank performance memory.
- Before the minimum comparable sample exists, memory contributes nothing to selection or writing.

## UI and credentials
- Adds a dedicated `Редакційна пам'ять` tab with learning state and the current TOP posts with their real metrics.
- Adds one-time Telegram Analytics authorization using API ID, API Hash, phone, login code and optional Telegram 2FA password.
- API Hash and Telegram StringSession are stored in the existing AES-GCM encrypted secrets store.
- A manual `Оновити статистику зараз` action is available in addition to automatic background refresh.

## Cache and compatibility
- Rewrite format marker advances to `telegram-post-v30` so RC47 cached copy is not reused as an RC48 editorial-learning result.
- Existing Data is preserved. RC48 adds its `telegram_metrics` table automatically on first start.
- Existing channels, sources, editorial profiles, weights, publication history, Bot Tokens and AI credentials remain compatible.

## Upgrade
Unpack RC48 into a fresh folder and copy the complete existing `Data` directory from RC47. Do not overlay the program/runtime files. After first start, open `Редакційна пам'ять` and authorize Telegram Analytics once if you want automatic performance learning.
