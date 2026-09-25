UA FREE Telegram Autopilot v2.0.0-rc86 — MANUAL TEST

RC86 is based on RC85.

Changes:
- adds a generic per-source setting “Заборонити посилання у публікації з цього джерела”;
- when enabled, URLs are removed from the article body and no source/footer/video link is added to the Telegram publication;
- existing ZaBor sources are seeded with this flag once during upgrade, then the operator setting remains authoritative;
- internal canonical source URLs remain available for dedupe, evidence and media handling;
- RC85 polling, incident clustering, editorial review and local learning remain unchanged.
