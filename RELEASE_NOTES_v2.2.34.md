# Autopilot 2.2.34 — independent Drive authorization and verified split monitoring media

Date: 2026-10-25. Candidate, NOT operator-installed. Release only after CI/native Windows/Defender and official signed Portable assets succeed.

## P0 Google Drive security / resilience
- Removed automatic scan/decrypt of sibling Content Tool configuration and removed silent cross-application refresh token persistence from `drive_api_telemetry`. Only Autopilot encrypted secrets or explicitly provided Autopilot environment settings are selected.
- Kept any already saved Autopilot refresh token as legacy-unverified during migration. It may historically have originated from Content Tool; until the operator explicitly completes **Autopilot's own Google OAuth flow**, independent authentication is NOT guaranteed. No forced logout or destructive secret rewrite.
- Prominent Google Drive entry, Connect/Test, last API success/error, and migration notice in Autopilot UI; dedicated independent Google OAuth Desktop client ID is recommended. Upon successful own authorization, origin is `autopilot-oauth`.
- **No coupling between Telegram publishing and Drive telemetry**. Failure to write cloud files should be diagnosed separately from channel health. Local fallback is NOT proof of cloud success.

## Monitoring media integrity
- Added explicit *same-channel, media-referenced Telegram URL* ownership between a text post and distinct photo/video message; only on positively expressed attachment references, not mere adjacent IDs/timestamps. Exact missing post may be retrieved by ID with bounded requests.
- The final media publication guard accepts genuinely linked monitoring media with complete source-message provenance, rather than silently discarding it when the primary exact text post has fewer attachments. Neighboring unrelated media remains rejected; no new automatic replay of already published items.
- Remaining limitation: where source media and separate text have NO verifiable album/reply/source-media URL binding, program cannot safely invent ownership. Such media is still marked unresolved for investigation, not arbitrarily joined. This is especially relevant to user-reported Благовіщенська сільська військова адміністрація case; post IDs / ownership markup not independently verified from screenshots alone.

## Release acceptance
- Regression tests: isolated credentials, expired token without borrowed Content Tool fallback, preserving migration credentials, positively linked media, unrelated media refusal, monitoring vs editorial separation.
- GitHub CI 4/4, Windows portable build, Defender scan, and official GitHub assets+SHA256 must all succeed before official declaration.
- Operator: backup complete original Data, stop running Autopilot, install official ZIP in new folder, import original Data, sign into **Autopilot Google Drive** with its own Desktop client, check cloud file modifiedTime advances twice and active source/collectors 3/3. Keep sources 36/18/57, cadence 45/30/5, $3 daily/$20 monthly AI budget, receipts and quarantined UNKNOWN #66297 unchanged.
- No remote operator patch, no automatic data deletion, no forced resend.
