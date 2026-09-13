# UA FREE Telegram Autopilot V2.0.0-rc24

Фінальна збірка цього циклу після живої перевірки RC21.

## Дистанційний нагляд
- Один робочий Google Drive transport: `SUPERVISOR FEED — Autopilot V2 LIVE`.
- Supervisor публікує lifecycle state і монотонний sequence, щоб віддалений агент бачив тільки свіжі snapshots.
- Runtime/stop state синхронізований з фактичними workers/collectors.

## Медіа
- EDITORIAL: максимум одне релевантне медіа.
- MONITORING: тільки медіа точного Telegram `data-post`; avatar/logo/reply/forward/link-preview не проходять.
- Permanent required-media misses більше не зависають нескінченно в WAITING/MEDIA.

## UI
- Збережений responsive UI: важкі refresh/start/stop операції не блокують Tk main thread.
- UI heartbeat доступний Supervisor для виявлення `UI_STALLED`.

## Оновлення
- SHA-verified update overlay, quiesce, SQLite checkpoint/backup, startup health gate та rollback.
- GitHub є джерелом release artifacts; Google Drive використовується як transport для supervisor/agent/update manifest.
