# UA FREE Telegram Autopilot V2.0.0-rc22

## Telegram media fix

- Виправлено головну регресію RC19-RC21: реальне медіа більше не залежить від нестабільного positive allowlist класів Telegram.
- Межа ownership тепер сама картка exact `data-post`: медіа приймається тільки всередині конкретного поста, а сусідні повідомлення як і раніше ніколи не донорять вкладення.
- Avatar/channel photo, reply/forward preview, link/webpage preview, reaction, video poster, promo/sponsor/subscribe/follow chrome відсікаються по ancestor blacklist.
- Невідомий новий wrapper Telegram усередині exact post більше не означає автоматичну втрату справжньої картинки.
- `media_filter_version=4`; існуючі v3 пости з валідним медіа залишаються сумісними, а заблоковані `MEDIA_REQUIRED` автоматично розблоковуються після свіжого source refresh, якщо медіа з'явилося.

## Дистанційний нагляд

- Збережено RC21 Google Drive supervisor feed, agent journal/hourly report, UI heartbeat, update status і Drive-first SHA-verified updater.
- RC22 не змінює робочий транспорт нагляду: `status.json`, `incident.json`, `recent_events.json`, `agent_events.jsonl`, `agent_journal_since_review.json`, `hourly_latest.json` продовжують дзеркалитися у `SUPERVISOR FEED — Autopilot V2`.

## UI

- Збережено nonblocking Start/Stop, active-tab refresh та короткі UI SQLite reads з RC20/RC21.
