# UA FREE Telegram Autopilot v0.1.0-rc29

Windows portable застосунок для збору технологічних/наукових новин, AI-рерайту українською, фактологічного та мовного QA і прямої публікації в Telegram.

## Поточний production-конвеєр

`джерело → очищення статті → exact/title/event dedupe → Evidence Pack → AI Router → Fact Guard + український QA → LanguageTool (якщо готовий) → Telegram`

## AI Router

- Google Gemini, NVIDIA NIM і Groq тепер читають актуальні каталоги моделей через API та формують runtime-список моделей автоматично.
- Якщо каталог провайдера недоступний, використовуються перевірені fallback-ID.
- Ліміт однієї моделі не блокує автоматично всі інші моделі того самого провайдера.
- Cloudflare лишається на статичних моделях, бо сумісний стабільний model-list endpoint у цьому контурі не використовується.
- Локальний fallback: Ollama → запасний llama.cpp.
- Кнопка «Знайти локальні моделі» показує реально встановлені Ollama-моделі та може запустити встановлену Ollama, але нічого не завантажує.

## LanguageTool

- Працює локально на `127.0.0.1:8081` і не є блокером живучості автопілота.
- Java/LanguageTool запускаються портативно з `Data/Tools` і завершуються разом із програмою.
- UI показує накопичувальну кількість реальних перевірок, виправлень та останню застосовану правку.
- Статистика зберігається у `Data/Tools/languagetool_stats.json`.
- Навіть без LanguageTool перед публікацією працюють deterministic Ukrainian fixes, hard-language blockers, number/year QA і Fact Guard.

## Черга та джерела

- `new` має пріоритет над `retry`; серед `new` першими обробляються найсвіжіші матеріали.
- Один складний матеріал має обмежений AI/QA budget і не повинен забирати весь цикл.
- Свіжі технічні AI/QA помилки після переходу на RC28 один раз повертаються в `new` для чистої повторної обробки.
- Для web-page джерел, що відповідають HTTP 403/429, Autopilot пробує типові публічні RSS/Atom endpoints як fallback.
- Налаштована «Мін. пауза між постами» лишається свідомим обмеженням частоти Telegram-публікацій.

## Що прибрано

- runtime Telegraph;
- старий `decision_engine.py`;
- UI-костиль `ui_direct_format.py`;
- старе ім'я `production_pipeline_rc9.py` (активний модуль тепер `production_pipeline.py`);
- накопичені release notes RC9–RC27 і старі RC9 gate-файли;
- версійні one-time cooldown-міграції з `service.py`.

Історичні `telegraph_*` поля SQLite не виконують код і залишені лише для безпечного читання існуючої `Data` без destructive migration.
