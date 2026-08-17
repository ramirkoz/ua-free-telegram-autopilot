# UA FREE Telegram Autopilot v0.1.0-rc9

## Live hotfix 17.08.2026

RC9 зберігає той самий внутрішній номер версії та сумісність з наявною `Data`, але містить виправлення, знайдені під час живого Windows-тесту.

### Черга
- свіжі `new` матеріали обробляються раніше за старі `retry`;
- retry має backoff 2 / 5 / 15 / 30 хвилин;
- після 5 невдалих повторів матеріал переходить у `error` і більше не блокує потік;
- існуюча база мігрується лише additive-полями `retry_count` і `next_retry_at`.

### AI Router
- вилучені NVIDIA-моделі, які у live-тесті повернули HTTP 410 / end-of-life;
- робочі Nemotron/Groq routes залишені у production chain;
- quota/429 ставить провайдера на cooldown для поточного failover, а не змушує наступні матеріали знову бити той самий ліміт;
- editorial decision більше не вимагає бездоганного JSON: використовується компактний `PUBLISH / REJECT / DUPLICATE` line protocol із tolerant parsing;
- rewrite використовує `ЗАГОЛОВОК / АНОНС / ТЕКСТ`, JSON лишився сумісним fallback;
- local Ollama prompt істотно скорочений, local task bounded timeout;
- один цикл обробляє обмежену кількість AI-спроб і має wall-clock deadline.

### Media
Зберігаються RC9 правила safe media selection: реклама, Cocoon/AI-summary, банери, логотипи, аватарки та tracking assets не використовуються як editorial media. Якщо надійної картинки немає, Telegram-публікація виконується без випадкового зображення.

### Перевірки
- локальний source gate: 19 tests PASS;
- extracted Source ZIP: 19 tests PASS;
- GitHub Actions: Ubuntu/Python 3.12 PASS;
- Windows/Python 3.11 PASS;
- Windows/Python 3.12 PASS;
- Windows/Python 3.13 PASS.

Живий publication gate на реальній `Data` залишається фінальною перевіркою перед визнанням RC9 стабільним.
