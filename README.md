# UA FREE Telegram Autopilot v0.1.0-rc21

Окремий Windows portable продукт для автоматизованого збору, редакційної обробки та прямої публікації технологічних і науково-популярних новин у Telegram.

## RC21 language-quality hotfix

- Conservative deterministic cleanup of live-observed Ukrainian spelling/russism errors before publication.
- Optional copy-edit pass now targets spelling, idiom, calques and unsupported evaluative wording as well as agreement.
- Non-attributed hype sentences such as «один з найкращих» are dropped rather than presented as facts.
- Language repair is revalidated through the existing year/number/Fact Guard checks and remains non-blocking when a copy-edit provider is unavailable.

## RC20: liveness + Ukrainian QA + fact-relation repair

RC20 is based only on the live-tested RC19 portable. It fixes the remaining failure pattern where technical Ukrainian posts were falsely rejected, temporary endpoint failures exhausted the article deadline before local fallback, and a wrapped provider outage could turn many following fresh stories into identical retry rows. It also tightens relation-preservation after the live TerraPower post exposed a coolant/storage and agreement/purchase binding error.

- Ukrainian language detection now works at word/function-word level and tolerates Latin product/model/company names.
- A healthy cloud model gets one targeted repair turn for soft format/language/length QA before that model is skipped.
- Network failures create a short provider-level cooldown for shared endpoints, avoiding repeated timeouts on a second model at the same endpoint.
- The last successful cloud provider/model is preferred, while local remains an emergency fallback and receives reserved deadline time.
- Post-AI QA propagates provider-outage state so the service pauses the cycle after one affected article instead of poisoning the remaining `new` queue.
- Main rewrite instructions explicitly preserve subject/object/component relations and agreement-vs-purchase strength.
- Fact Guard blocks observed relation-strengthening errors such as deployment agreements rewritten as purchases and sodium-cooling confused with molten-salt storage.
- Longer finished posts receive an optional bounded grammar proofread, revalidated by the same factual guards; proofread failure never blocks an already-safe candidate.
- Pending/retry cache format advances to `telegram-post-v11`.

## RC15: provider health separated from post-AI QA

RC15 fixes the live failure mode where a healthy provider response could be treated as a provider failure merely because an article-specific format, Fact Guard, language, completeness or length check rejected the candidate. Provider diagnostics now require a successful endpoint/auth response and non-empty text, not an exact magic phrase. Production routing obtains raw model output first; article QA runs afterwards and can request another model without changing provider health. A single bounded local format-repair turn remains available as post-AI QA.

## RC13: event dedupe + Ukrainian grammar assurance

RC12 відновив живу публікацію через AI Router. Live-тест RC12 показав два наступні дефекти якості: різні джерела могли окремо опублікувати одну й ту саму подію, а Fact Guard/readability не ловили окремі помилки граматичного узгодження українських закінчень.

RC13:

- зберігає title/exact dedupe, але додає high-precision event-level порівняння фінального українського рерайту з уже опублікованими текстами;
- повторює event-level dedupe безпосередньо перед Telegram write, тому старий `retry` із кешованим рерайтом не може наздогнати вже опублікований матеріал про ту саму подію;
- порівнює до 80 свіжих опублікованих матеріалів у межах налаштованого `dedupe_window_hours`;
- явно вимагає в основному rewrite prompt перевірити рід, число, відмінок, підмет-присудок, прикметник-іменник, займенники та керування прийменників;
- для синтаксично ризикового тексту може виконати короткий grammar proofread іншим cloud-провайдером;
- приймає proofread тільки після повторного Fact Guard/number/year QA та перевірки збереження чисел, Latin entities і основного змісту;
- не блокує публікацію, якщо додатковий grammar provider недоступний;
- використовує `telegram-post-v6`, тому pending/retry кандидати RC12 переписуються за новими правилами перед майбутньою публікацією.

## Збережений RC12 AI Router liveness fix

- article-specific Fact Guard / format / number / readability failure не створює provider/model cooldown;
- зміни `ai_router_state.json` серіалізовані та не перезаписують свіжий стан старим snapshot;
- прострочені cooldown-и прибираються автоматично;
- cooldown лишається тільки для реальних health-проблем: quota/auth/network/model/runtime;
- local Ollama/llama.cpp при реальній недоступності має короткий cooldown.

## Production-конвеєр

`джерело → очищена стаття → exact/title dedupe → Evidence Pack → AI-рерайт → Fact Guard + grammar/readability QA → event-level dedupe → один медіафайл або без медіа → Telegram`

Ключові правила:

- прямий Telegram, без Telegraph у production pipeline;
- без окремого заголовка;
- медіа: один релевантний файл + до 900 символів;
- без медіа: текст до 4096 символів;
- `new` має пріоритет над `retry`;
- retry має bounded backoff і cap;
- Telegram publisher, Media Engine, source collection, SQLite schema та AES-GCM secrets не переписані;
- існуюча portable `Data` сумісна без destructive migration.

Поточна версія: `0.1.0-rc21`.


## RC22 media priority
Embedded YouTube/Vimeo/HTML5 video is preserved as editorial media. Trailer/video stories prefer the embedded video; YouTube uses a thumbnail plus watch link when Telegram cannot embed the player directly.

## RC24 — автоматичний LanguageTool

RC24 автоматично забезпечує локальний LanguageTool для української граматики:

- при старті Autopilot перевіряє `127.0.0.1:8081` у фоновому потоці;
- якщо LanguageTool відсутній, завантажує офіційний snapshot у `Data/Tools/LanguageTool`;
- якщо немає Java 17+, завантажує портативний Eclipse Temurin JRE 17 у `Data/Tools/Java17`;
- системна Java, реєстр Windows і права адміністратора не потрібні;
- зовнішній LanguageTool cloud API не використовується;
- після копіювання всієї `Data` в нову portable-версію LanguageTool та Java переносяться разом з нею;
- якщо інтернет тимчасово недоступний, Autopilot не блокує поточний матеріал і повторює встановлення не частіше ніж раз на 5 хвилин.
