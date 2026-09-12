# UA FREE Telegram Autopilot v2.0.0-rc18

## Що виправлено

- Telegram ingest більше не вважає аватар/логотип каналу медіа публікації: фільтр перевіряє CSS-класи не лише самого `<img>`, а й усіх батьківських елементів.
- Video thumbnail/poster більше не додається як окреме фото поруч із реальним відео. Якщо доступне справжнє `<video>/<source>`, у bundle потрапляє відео; poster не публікується.
- Link preview, reaction/emoji/avatar chrome відсікаються до MediaBundle.
- Додано telemetry `raw_candidates / discarded_non_content / discarded_video_thumb / discarded_duplicate / content_media` у Telegram layout і Supervisor status.
- Для Telegram повторний ingest тепер **замінює** source media snapshot замість merge зі старим `media_json`, тому сміття RC17 не накопичується.
- Одноразова startup-санітизація очищає непубліковані pre-RC18 Telegram media snapshots; опубліковану історію не змінює.
- MEDIA-blocked job розблоковується повторним ingest лише якщо після фільтра реально є медіа.
- `source_published_at` нормалізується в ISO при ingest. TTL expiration тепер парсить і ISO, і RFC2822 у Python, тому старі jobs більше не живуть понад `max_age_hours` через обмеження SQLite `datetime()`.
- Legacy Telegram parser синхронізований з новим avatar/video-poster filter.

## Незмінний контракт публікації

- 1 медіа + текст: один Telegram-пост, caption до 900 символів.
- Кілька реальних медіа: media group + caption, без окремого текстового повідомлення.
- `required / preferred / optional` задається налаштуваннями каналу, без hardcode.
- Media-only + adjacent text-only у Telegram-джерелі склеюються в одну логічну публікацію.
