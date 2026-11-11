# UA FREE Telegram Autopilot v2.3.26 — emergency UI hotfix
Date: 2026-11-11. Based on 2.3.25, no feature/policy changes.

## Confirmed root cause
Toolbar "Тест усіх AI" called MainWindow.test_ai, which referenced `self.status_text` despite Tk UI providing `self.status`. The AttributeError occurred before the probe worker thread started. Operator repeatedly clicked (5 times) with no "manual AI all providers test started" event, and direct routes continued showing STALE. Separate OpenRouter manual test succeeded.

## Repair
Use actual V2 UI status variable, call AIGateway.probe_all once in a background thread and update visible result + AI tab on Tk thread. Prevent repeated clicks from starting parallel paid API tests. Log button press and explicit results/error. The model/provider network code and keys are unchanged.

## Evidence
18 targeted offline tests passed (15 inherited + 3 dedicated toolbar tests); ZIP file CRC passed. User's direct providers are NOT yet verified via API. A new Windows run and single successful click must produce "manual AI all providers test started/finished" and per-provider result codes.

## Preserved
Operator Data/secrets, prior Telegram receipts UNKNOWN, no replay, 45/30/5 minutes, media/facts, $3/day/$20/month budgets and 08:58 fixed daily post. No configuration changes or remote operator install. NOT LIVE VERIFIED.
