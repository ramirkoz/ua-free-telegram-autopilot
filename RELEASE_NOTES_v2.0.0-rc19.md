# UA FREE Telegram Autopilot v2.0.0-rc19

## Виправлено медіаконтракт

- **EDITORIAL знову має жорсткий контракт: одна публікація = рівно одне найкраще медіа.** Навіть якщо джерело містить галерею, рекламні блоки або кілька валідних зображень, у редакційний канал іде лише перше очищене editorial media. Publisher більше не може самовільно перетворити редакційний пост на карусель.
- Для веб/RSS редакційний snapshot обрізається до першого очищеного кандидата, тому друге/третє службове або промо-зображення більше не може перетворити пост на карусель.
- Повторний web/RSS ingest більше не накопичує старі media URL. Свіжий непорожній snapshot **замінює** попередній; старий зберігається лише коли поточне читання тимчасово не дало жодного медіа.

## Telegram monitoring: media ownership v3

- Межа `data-post` тепер є авторитетною: медіа може потрапити до публікації лише з того самого Telegram widget, де знаходиться текст.
- Видалено RC18-евристику «сусідні message ID + до 5 хвилин = одна публікація». Сусідній media-only пост більше не може подарувати картинку іншій новині.
- Додано positive ancestry allowlist для реальних Telegram photo/video/grouped/document containers. Аватари, логотипи каналу, reply/forward chrome, link previews, reactions, emoji та video posters відсікаються до `MediaBundle`.
- `media_filter_version=3`; усі непубліковані Telegram snapshots попередніх версій очищаються один раз і мають бути перечитані з джерела.
- MONITORING як і раніше може публікувати всі **реальні** медіа одного оригінального поста; EDITORIAL ніколи не успадковує цю поведінку.

## Безпечне агентне оновлення

- Додано локальний детермінований `UpdateProtocol`: агент може передати лише `target_version + SHA256 + request_id`. Довільні URL, shell-команди та файлові шляхи не приймаються.
- Update asset завжди будується тільки з фіксованого репозиторію `ramirkoz/ua-free-telegram-autopilot` та version-tagged GitHub Release.
- Перед оновленням Autopilot переходить у `QUIESCING`: припиняє runtime, дочікується worker/collector, робить SQLite WAL checkpoint і консистентний backup БД.
- Файли програми оновлює окремий helper **після завершення основного процесу**. `Data` ніколи не входить до update bundle і не перезаписується.
- Update ZIP перевіряється за SHA-256, version metadata, структурою та `UPDATE_RUNTIME_ABI`. Оновлення, яке потребує нового Python/runtime ABI, відхиляється і має встановлюватися повним portable release.
- Після запуску нової версії helper чекає `startup_healthy.json`. Якщо startup/DB maintenance не проходить, файли та база автоматично відкочуються і запускається попередня версія.
- У тій самій Supervisor/Google Drive mirror-папці з’являються `update_status.json`, `update_ready.json` і `update_result.json`, тому агент бачить `REQUESTED / QUIESCING / READY_FOR_UPDATE / DOWNLOADING / APPLYING / HEALTHY / ROLLBACK_OK / FAILED` без вгадування по логах.

## Release update asset

Після успішного стандартного Windows release окремий workflow додає до того самого GitHub Release:

- `UA_FREE_Telegram_Autopilot_v2.0.0-rc19_Update.zip`
- `UA_FREE_Telegram_Autopilot_v2.0.0-rc19_Update_SHA256.txt`

Цей overlay призначений для автономних оновлень **після встановлення RC19**. Перехід з RC18 на RC19 виконується звичайним portable release, після чого наступні сумісні RC можуть оновлюватися через агентний протокол.
