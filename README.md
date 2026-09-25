# UA FREE Telegram Autopilot v2.0.0-rc89

Windows Portable автопілот для збору, відбору, редактури та публікації контенту в Telegram з опційним кроспостингом у Facebook.

## Архітектура

- `telegram_autopilot/v2` — активний runtime, канали, черга, editorial pipeline, Supervisor та updater.
- `Data` — тільки користувацькі дані: база, конфігурація, журнали, кеш і службовий стан.
- `Tools` — відтворювані важкі інструменти: LanguageTool, JRE і Codex. Вони не входять у Data і не мігруються зі старих версій.
- Anti-Slop, мовні/граматичні блокери, paragraph/corruption QA та фактова перевірка працюють у фінальному V2 editorial pipeline.
- AI Router використовує зовнішні провайдери та local fallback; Codex через ChatGPT є резервним trusted provider, а не першим маршрутом для кожної дрібної задачі.

## Перший запуск / міграція

Нова чиста папка не потребує копіювання старої `Data`. На першому запуску можна вказати стару папку Autopilot або її `Data`; імпортер у режимі read-only переносить лише довготривалі дані: канали, правила, джерела, історію матеріалів/публікацій, feedback та зашифровані credentials. Логи, cache, Tools, provider cooldowns і runtime queues не переносяться.

## Portable layout

```text
UA_FREE_Telegram_Autopilot.exe
_runtime/
Tools/
Data/
VERSION.txt
PUBLIC_VERSION.txt
V2_VERSION.txt
README.txt
```

При штатному оновленні `Data` і `Tools` зберігаються. При закритті V2 runtime явно завершує власний LanguageTool JVM, щоб стара папка не залишалася заблокованою `java.exe`.

Поточний реліз: **v2.0.0-rc89**.
