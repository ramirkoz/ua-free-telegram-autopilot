# UA FREE Telegram Autopilot v2.0.0-rc20

## Медіа: жорсткий контракт без «воскресіння» другої картинки

- **EDITORIAL = максимум одне релевантне медіа на всіх рівнях.** RC19 міг залишити одну картинку в `media_json` і іншу в layout, після чого publisher знову збирав дві. RC20 робить один семантичний вибір і зберігає той самий елемент в обох представленнях.
- Для редакційних web/RSS матеріалів фінальний вибір використовує перевірений semantic media gate: відсікає banner/follow/subscribe/logo/avatar/sponsor/promo/recommendation chrome, звіряє metadata з темою матеріалу і віддає тільки один hero.
- Якщо релевантне медіа не підтверджене, редакційний канал не отримує випадкову картинку. `required` блокує публікацію, `preferred/optional` можуть перейти в текст.
- MONITORING не втрачає реальні альбоми. Один Telegram `data-post` лишається єдиною межею ownership; сусідні media-only повідомлення не склеюються.
- Розширено відсікання Telegram avatar/channel-photo/reply/forward/link-preview/webpage-preview контейнерів.

## Наглядач + agent feed + Google Drive

- Наглядач веде `status.json`, `incident.json`, `recent_events.json`, обмежений `history.jsonl` і persistent state інцидентів.
- Доданий локальний **Agent Feed**: `agent_events.jsonl`, `agent_journal_since_review.json`, `agent_request.json`, `hourly_latest.json`, `review_ack.json`.
- Agent Feed фіксує дельти статей/публікацій/черги/AI/media/source errors, активні інциденти, UI lag і стан оновлення.
- При інциденті автоматично формується `agent_request.json` для віддаленого аналізу; при відновленні стан зберігається, а journal не губиться.
- Supervisor намагається сам знайти папку **SUPERVISOR FEED — Autopilot V2** у типових Google Drive Desktop шляхах. Відсутній або зламаний mirror тепер є видимим інцидентом, а не мовчазним провалом.

## Безпечне автооновлення

- Збережено RC19-модель `QUIESCING → SQLite checkpoint/backup → detached updater → startup health → rollback`.
- Додана підтримка `release_manifest.json` у Drive за моделлю KONTUR: автооновлення приймається тільки коли `approved_for_auto_update=true`, `ci_passed=true`, `windows_build_passed=true`, версія новіша, asset має очікуване фіксоване ім'я і SHA-256.
- Manifest не може передати shell-команду, локальний шлях або довільний URL. Download URL як і раніше будується тільки для `ramirkoz/ua-free-telegram-autopilot`.

## UI responsiveness

- Прибрано старий цикл, який кожні 2.5 с синхронно перемальовував **усі** вкладки і понад тисячу Treeview-рядків на Tk main thread.
- Оновлюється лише активна вкладка з окремими TTL: важкі `Черга`, `Історія`, `Статистика` не перераховуються, коли користувач їх не дивиться.
- Черга обмежена 200 рядками, історія 250, навчання 120.
- UI-read SQLite використовує короткий busy timeout: пропускається один refresh, замість Windows `Not responding` на 30 секунд.
- Start/Stop runtime винесені з Tk thread. Зупинка workers більше не блокує GUI.
- Tk heartbeat пишеться кожні 0.5 с; Supervisor піднімає `UI_STALLED`, якщо інтерфейс реально перестав відкликатися.

## Regression

Додані перевірки на:
- різні media у `media_json` і layout не можуть утворити редакційну карусель;
- один вибраний editorial media зберігається однаково в обох durable representations;
- monitoring album лишається багатомедійним;
- approved Drive manifest перетворюється тільки на fixed-repository update request;
- Supervisor бачить завислий Tk heartbeat.
