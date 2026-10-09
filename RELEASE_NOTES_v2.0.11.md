# UA FREE Telegram Autopilot 2.0.11

## Web media repair

- Preserves vetted first-party hero/featured images even when the publisher supplies a generic image filename or alt text. The article extractor must establish article identity; hard-noise filtering and local binary/image validation remain mandatory.
- Recovers source-owned image candidates from stored media JSON even when article HTML also contained an iframe or other unusable media block.
- Preserves schema.org Article image galleries where the schema node is demonstrably tied to the current article. Removes the unsafe fallback that trusted an unmatched singleton Article node.
- Adds conservative perceptual image deduplication for resized or near-identical photographs within one article, in addition to URL and exact binary hashing. Different photographs are not collapsed by image dimensions alone.
- Separates raw extracted media count, filtered count and classifier failure diagnostics in publication telemetry. A validator error is not misreported as a story that had no media.
- Preserves existing video link/poster behavior, per-channel media policies and previously published history. This release does not clear the queue or modify channel settings.

## Acceptance

- CI tests across Ubuntu and Windows, full Windows Portable packaging and native GUI/credential smoke required.
- Live acceptance separately checks web-based publications with their real source hero/gallery/video, visual uniqueness, no cross-story images, and correct Telegram media count.
- The first clean-queue reset remains a 2.0.10-only migration; it is not repeated by 2.0.11.
