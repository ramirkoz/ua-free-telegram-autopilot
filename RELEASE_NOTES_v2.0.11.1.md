# Autopilot 2.0.11.1

Hotfix for web image Unicode URLs. HTTP request targets now percent-encode non-ASCII path and query characters before sending to http.client, preserving original percent escapes and separators. Fixes observed 2.0.11 `UnicodeEncodeError` on article 37472 (12 raw image candidates; URL included U+2014 em dash). Includes no-network regression tests for Cyrillic and em dash image URLs and already escaped URLs.

Preserves 2.0.11 web hero/gallery, video and dedup work. No queue reset or configuration changes. CI, full Windows portable build and first operator-run acceptance required.
