# UA FREE Telegram Autopilot 2.1.2 — embedded video links

Status: release candidate; CI, Windows artifact verification and operator live QA required.

## Changes
- Normalize multiple source-owned YouTube and Vimeo embeds, including Shorts, youtube-nocookie and lazy attributes.
- Preserve video_links and video_embed_count in article layout and publication bundle.
- Include each distinct verified video URL in the Telegram attribution footer.
- Photo with source video URLs is classified as VIDEO_LINK_ONLY, not video delivered.
- Tests: 3 independent Robitussin-style embeds and lazy Shorts; exclude sidebar recommendations.
- The actual The Drum page remains operator acceptance fixture; synthetic tests do not prove live publisher DOM extraction.

## Not changed
- Source identity and cross-campaign media safeguards; Data and channel settings; Content Tool RC60.
- X/Reddit viral-topic discovery planned for 2.1.3.
- Manual Portable install preserving Data until signed updater verified.