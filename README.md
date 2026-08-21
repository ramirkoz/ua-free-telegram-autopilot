# UA FREE Telegram Autopilot v0.1.0-rc32

Windows portable застосунок для збору технологічних/наукових новин, безпечного AI-рерайту українською та прямої публікації в Telegram.

## Production-конвеєр RC30

`джерело → очищення → exact/title/event dedupe → Evidence Pack → reviewed AI writer → Fact Guard → trusted editor за потреби → Ukrainian hard gate → optional LanguageTool → Telegram`

### AI Router

- Production використовує лише статичний allowlist перевірених моделей. Автоматичне додавання випадкових моделей із provider `/models` у unattended publication вимкнено.
- Пріоритет стабільний: Codex/ChatGPT → Gemini → reviewed NVIDIA/Groq/Cloudflare → local Ollama/llama.cpp.
- Відновлений Codex знову є першим production writer; старий quota cooldown Codex обмежено приблизно 5 хвилинами, щоб відновлений ChatGPT-ліміт не залишався прихованим.
- Остання випадково успішна fallback-модель більше не стає автоматично першим writer наступної новини.
- Якщо перший придатний draft створив NVIDIA/Groq/Cloudflare/local, він не може піти в Telegram напряму: фінальний текст повинен підтвердити trusted editor Codex або Gemini.
- Якщо trusted editor недоступний, матеріал іде в bounded retry, а не в autopublish.

### Editorial safety

- Fact Guard, number/year checks, attribution/relationship protections залишаються hard gates.
- Додано загальний structural corruption gate: зациклені фрази, повторені речення/слова, аномально низька лексична різноманітність, домінування однієї словоформи/основи, Russian-only letters, злиті Latin+Cyrillic слова, незакриті лапки.
- Технічні форми на кшталт `AI-сервіс`, `OAuth-потік`, `Xtra-версія` не блокуються лише через різні абетки по обидва боки дефіса.
- Фінальний deterministic editorial threshold: 82/100. Старий аварійний fail-open поріг 58 прибрано.
- LanguageTool лишається локальним додатковим proofreader, але не є єдиною лінією захисту: після нього знову працюють Fact/UA/structural gates.

### Source health

- HTTP 429 отримує 20-хвилинний backoff, HTTP 403 — 10 хвилин, тимчасова network/DNS помилка — 3 хвилини.
- Backoff читається з уже наявного `source_health`, тому перезапуск програми не змушує одразу знову бити rate-limited джерело. Ручний цикл `Перевірити зараз` свідомо обходить цей backoff.

### Dedupe

- Збережені exact/title/high-precision event правила.
- Додано safe cross-length event rule для ситуації, коли перший короткий матеріал і пізніший довший follow-up описують ту саму конкретну подію.
- Pending/retry rewrite cache marker піднято до `telegram-post-v17`, тому незапубліковані RC29-кандидати не обходять новий RC30 editorial pipeline після перенесення `Data`.

### Діагностика

У `telegram_autopilot.log` тепер видно production route без текстів/секретів:

- provider/model AI attempt;
- transport/provider failure;
- успішний generator;
- потребу trusted-editor pass;
- trusted editor provider/model;
- final editorial score, LanguageTool changes та довжину фінального body.

## Дані та portable-режим

Сумісність існуючої папки `Data` і SQLite-схеми збережена. Для оновлення розпакуйте RC30 в нову папку та перенесіть туди всю `Data` з RC29. Не накладайте runtime-файли поверх старої збірки.
