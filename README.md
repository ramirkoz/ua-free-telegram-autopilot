# UA FREE Telegram Autopilot v0.1.0-rc11

Окремий Windows portable продукт для автоматизованого збору, редакційної обробки та публікації технологічних і науково-популярних новин у Telegram.

## Що нового в RC11

RC11 є вузьким hotfix поверх live-accepted RC10. Він виправляє ситуацію, коли інтерфейс показував «Автопілот: працює», але production AI Router продовжував пропускати вже відновлені хмарні провайдери через старий persistent cooldown, а несправний локальний fallback міг знову гальмувати кожну нову статтю.

- успішний production-виклик очищає model-level і provider-level cooldown;
- успішний `Тест AI Router` одразу повертає провайдера в production routing;
- збереження або заміна AI-ключів очищає stale cooldown;
- при першому запуску RC11 з копією RC10 `Data` виконується одноразове очищення старого AI cooldown;
- невдалий Ollama/llama.cpp fallback отримує короткий 3-хвилинний cooldown замість повторного блокування кожної новини;
- Evidence Pack, Fact Guard, Telegram publisher, media fallback, dedupe, retry backoff і `Data` schema не змінені.

## Поточний production-формат

RC11 зберігає прямий Telegram-конвеєр RC10:

`джерело → очищена стаття → локальний editorial/dedup gate → Evidence Pack → AI-рерайт → Fact Guard/readability QA → один медіафайл або без медіа → Telegram`

Ключові правила:

- жодних Telegraph-сторінок у production pipeline;
- один Telegram-пост = професійний український научпоп/техножурналістський текст без окремого заголовка;
- якщо є медіа: один медіафайл + завершений пост до 900 символів;
- якщо медіа немає: одне текстове повідомлення до технічного максимуму Telegram, 4096 символів;
- незавершений AI-вивід не обрізається: він відхиляється та переписується;
- максимум один перевірений релевантний медіафайл;
- дати, роки, числа, назви/моделі та high-risk claims перевіряються детерміновано проти поточного джерела;
- AI Router використовує bounded failover, provider/model cooldown та локальний Ollama → llama.cpp fallback;
- `new` матеріали мають пріоритет над старими `retry`, повтори мають backoff і ліміт;
- існуюча portable `Data` зберігається без destructive migration.

Поточна версія: `0.1.0-rc11`.
