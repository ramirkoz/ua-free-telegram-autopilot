# UA FREE Telegram Autopilot 2.3.18

Scope: narrow LIVE-based hotfix of v2.3.17. No changes to publisher intervals (CTRL 45 / ПРОДАНО! 30 / ГРОМАДИ 5 minutes), channel settings, operator Data or Telegram delivery receipts.

- Regional source gate: reject unrelated weather reports with explicitly named nonlocal Ukrainian regions and no original-source Zaporizhzhia link. Avoid publisher-name geolocation and retain locally grounded forecasts/national public-benefit news.
- LIVE_NOW: distinguish prospective construction of a municipal modular shelter and its future public purpose ("перечекати повітряну тривогу") from genuine ongoing air-raid alerts. Do not relax threat/attack detection.
- Postfactum protection: same narrow source-only shelter distinction in secondary editorial safety without bypassing actual active-alert reporting.
- Mandatory media: keep MEDIA_DOWNLOAD_RETRY on its scheduled 10-minute backoff despite any feed re-poll or apparent valid source image URL; retry only when the existing READY queue's next_retry_at has elapsed. Do not publish incomplete image sets or force-send.
- Exact Ukrainian copy repair: normalize the attested "ви\nпав" split word into "випав" during pre-publication safe-copyedit.
- Regression tests: positive, negative and channel isolation checks for all these changes.

Known operations issue not overridden: ПРОДАНО! 0 postboot v2.3.17, The Dieline HTTP 403, commercial mandatory-media blockers; a source provider rejecting access is not a permission to work around it. AI 3/7 DEGRADED on last v2.3.17 live evidence without blocked AI jobs. Two existing UNKNOWN Telegram outcomes (including article #92213) stay protected and MUST NOT be automatically replayed. All release/code gates are not proof of operator LIVE or new post quality.
