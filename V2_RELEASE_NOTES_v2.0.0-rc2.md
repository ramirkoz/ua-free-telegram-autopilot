# UA FREE Telegram Autopilot V2 2.0.0-rc2

RC2 виправляє критичний Windows-баг імпорту старої Data, знайдений під час реального запуску RC1.

## Виправлено

- Міграція більше не використовує `os.replace()` для заміни живої V2 SQLite-бази.
- Імпорт будується в окремій тимчасовій SQLite, проходить `PRAGMA quick_check`, після чого переноситься через SQLite online-backup API.
- Перед імпортом поточна V2 база зберігається в `Data/migration_backups` також через SQLite backup, а не файлове копіювання живої БД.
- Після перенесення нова V2 база повторно проходить integrity/required-table validation.
- При помилці після створення backup стара V2 база відновлюється через SQLite backup.
- Для кожного імпорту використовується унікальна temp-база, тому залишок від попереднього невдалого запуску не блокує наступну спробу.
- Додано regression test, який навмисно ламає `os.replace` з Windows-подібним WinError 32 і перевіряє, що міграція все одно завершується успішно.
- Додано повторний імпорт при наявності старого `telegram_autopilot_v2.sqlite3.migration.tmp`.

## Успадковано з RC1

- Чистий V2 runtime без історичного `rcXX` patch stack.
- Durable queue з `stage / decision / blocked_by`, fresh-first та ізоляцією каналів.
- Єдиний AI health registry та автоматичне пробудження WAITING_AI.
- Monitoring із збереженими inclusion/exclusion rules та fail-closed при недоступному AI.
- Canonical source URL як жорсткий publication gate.
- Read-only legacy import каналів, джерел, policy, editorial settings, published history, dedupe/feedback та encrypted credentials.

## Як тестувати

1. RC1 не оновлювати поверх старої папки. Розпакувати RC2 у нову папку.
2. Запустити `UA_FREE_Telegram_Autopilot.exe`.
3. Вкладка `Міграція` → `Імпортувати стару Data` → вибрати Data робочої RC82.
4. Після успішного імпорту перевірити канали, джерела, policy та AI, потім запускати автопілот.
