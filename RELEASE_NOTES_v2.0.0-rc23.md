# UA FREE Telegram Autopilot V2.0.0-rc23

## Дистанційний нагляд

- RC23 використовує один однозначний Google Drive transport: `SUPERVISOR FEED — Autopilot V2 LIVE`.
- Старі дублікати `SUPERVISOR FEED — Autopilot V2` більше не вибираються як робочий mirror.
- Supervisor додає `lifecycle_state` та монотонний `transport.sequence`, щоб віддалений агент відрізняв реальний новий snapshot від старого кешу.
- Якщо runtime реально працює і stop не запитаний, snapshot не може помилково показувати `expected_running=false` через UI race.

## Медіа

- Збережено RC22 strict Telegram media ownership: медіа належать тільки точному `data-post`; avatar/logo/reply/forward/link-preview chrome не проходять.
- Для required-media MONITORING матеріалів, де strict filter підтвердив відсутність валідного source-owned media, RC23 більше не тримає нескінченний `WAITING/MEDIA` backlog. Такі матеріали детерміновано пропускаються/архівуються без повторних AI-витрат.
- EDITORIAL як і раніше має максимум одне релевантне медіа.

## UI / lifecycle

- Збережено responsive UI RC21/RC22.
- Production UI прив’язаний до RC23 supervisor до старту runtime, тому intended state публікується до запуску workers.

## Оновлення

- Збережено SHA-verified update overlay, quiesce, SQLite backup/checkpoint, health gate та rollback.
- Google Drive лишається transport для supervisor/agent/update manifest; GitHub лишається джерелом release artifacts.
