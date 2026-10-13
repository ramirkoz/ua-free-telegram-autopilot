# Autopilot 2.1.11 — Visual media deduplication

- Universal final Telegram-upload gate compares downloaded source images by conservative perceptual and coarse-color fingerprints; detects resized/recompressed versions where SHA-256 differs. Keeps largest-resolution image at original gallery position. Real distinct photos and videos are retained. No channel/source names hardcoded.
- Publication telemetry adds `visual_duplicates_removed` separately from `binary_duplicates_removed`.
- Regression tests cover resized same image, genuine separate gallery images and unchanged video.
- Root report: CTRL+UA article #51299 Tom's Hardware, 2026-10-13 17:21:53 Kyiv, Telegram #1284–1286, 3 copies of apparent same image. The actual three downloaded source binaries were not in the short supervisor telemetry, so the exact duplicate encoding/crop relationship remains a live validation condition. Conservative matching may not collapse strongly cropped pictures.
- Existing published posts will not be edited/deleted. Preserve `Data`, credentials and delivery ledger on manual Portable update. 2.1.10 remains rollback. Technical CI does not establish live editorial acceptance.
