# UA FREE Telegram Autopilot v2.3.21 — editorial recovery

**Release candidate, 09 November 2026.** Grounded in the operator's November 9 completed 87 labels (CTRL+UA 56 and ПРОДАНО! 31). The 169 regional-monitoring rows were **not** scored and do not train the editor.

## Fixes

- **LIVE selector actually uses the current editorial engine.** A legacy runtime monkeypatch previously bypassed the newer 2.3.20 human feedback and source-quoted independent second opinion for calibrated channels. The override now delegates calibrated channels to the modern selector while leaving uncalibrated behavior intact.
- **Do not auto-PUBLISH internally inconsistent low-confidence material.** For a primary PUBLISH with adjusted fit below 40, or a commercial agency appointment / auction-type headline, use an independently source-quoted second decision; reject safely if no valid evidence or AI is unavailable.
- **Reject concrete routine agency appointments that describe only future work**, even when the publisher calls an expected future campaign a creative platform. Do not turn this into a blanket ban on real launched campaigns.
- **Full first-party publisher article recovery before a short-RSS editorial REJECT**, with exact URL + title identity, bounded network fetch, original source timestamp unchanged and Fact Guard preserved; inaccessible/insufficient sources still fail closed. Applies to editorial channels, not Telegram monitoring.
- **Rolling 24-hour timestamp for editorials, not calendar-day rejection at midnight**, while respecting each configured channel age cap and preventing restart replay via source timestamp, checkpoint and discovery requirements. Monitoring retains its existing strict calendar-day safety.
- **Commercial false-duplicate guard**: webpage boilerplate terms such as 'here' and 'without' cannot serve as named actor or concrete object in the cross-source event fingerprint.
- **One targeted numeric QA salvage pass** re-generates from SOURCE when AI invents digits. Mandatory factual QA, overall budget and quality failure behavior remain unchanged.
- **New regression fixtures** for cross-midnight source, no old replay, concrete agency PR and cross-source calendar/agency false duplicate.

## Intentionally unchanged

Data and Tools preservation, two historical Telegram UNKNOWN delivery receipts, no historic replays, publication intervals 45/30/5 minutes, Fact/Media/Telegram safety, OpenRouter-only while healthy, daily/monthly budget, no automatic label ingestion into production database.

## Acceptance

GitHub PR source/Windows CI and release Windows Portable+Defender gates must pass before merging or tagging. Operator deployment and organic Telegram publication review remain separate stages; a successful build does not establish LIVE editorial quality.
