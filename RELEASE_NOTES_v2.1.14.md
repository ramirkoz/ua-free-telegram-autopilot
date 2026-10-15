# UA FREE Telegram Autopilot 2.1.14

## Windows Portable maintenance release

- **Codex install from the open GUI:** invoke bundled `_runtime_console.exe -I -m pip` instead of relaunching `UA_FREE_Telegram_Autopilot.exe` via `sys.executable` and triggering the singleton guard. If bundled Python is absent, show an explicit error instead of silently starting a duplicate GUI. Installer remains optional; normal AI routing works without Codex.
- **Stop circular media retries:** source refresh no longer clears a durable MEDIA_REQUIRED publication block when it supplies the **same** set of image URLs as the failed publication attempt. Genuinely new source media evidence can still unblock and recheck an article.
- Regression tests for portable installer command selection, unchanged-media permanent block, and new-media recovery wake.
- No changes to existing operator Data, channels, API credentials, scheduled posting, or Telegram delivery ledger. No remote commands enabled.

## Known limits

- Telegram split-post/photo-album bundling, sophisticated cropped-image duplicate detection, source-image relevance, and Ukrainian translation quality remain for subsequent releases.
- Historically blocked READY items can be re-evaluated only if valid new media appears; post migration does not rewrite/delete already published posts.
- Official validation requires GitHub source CI and Windows-native Release job before operator installation.
