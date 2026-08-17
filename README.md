# UA FREE Telegram Autopilot v0.1.0-rc9

## RC9: bounded AI Router + safe media engine

RC9 is a compatibility-preserving stabilization release. Existing `Data` from RC8 is reused as-is; there is no database reset or destructive migration.

- AI Router adopts the bounded production design proven in UA FREE Content Tool v1.2.2: per-task output budgets, cloud timeouts, overall deadlines, quota cooldowns and installed Ollama as the last local fallback.
- Ollama is detected on `127.0.0.1:11434`; the app may start an already installed `ollama serve`, uses existing generation models and never installs Ollama or downloads models. The existing loopback llama.cpp fields remain a manual fallback.
- Editorial decision and Ukrainian rewrite are split into separate bounded AI tasks, so duplicate/history classification no longer drags a full Telegraph rewrite through every provider.
- Ukrainian terminology QA blocks known production calques and normalizes standard terms such as `даркнет` and `електронно-променева трубка (ЕПТ)`.
- Media selection no longer trusts `og:image` as the automatic hero. Ads, Cocoon/AI-summary assets, banners, logos, avatars, tracking images and other non-editorial candidates are rejected. Body editorial images are ranked against title/article context, and an irrelevant image is replaced by **no media**, not by a random banner.
- Captions are conservative: AI may translate/shorten source caption/alt metadata, but a caption is dropped when source metadata is absent or the generated caption invents numbers/strong claims.
- Telegram hero is the highest-scoring validated source image rather than simply the first/featured image.

### Data compatibility

RC9 deliberately keeps the RC8 database schema and secret-file format unchanged. Copy the complete existing `Data` directory next to the RC9 executable. Do not copy only the SQLite file: tokens/keys live in the same `Data` directory.

## RC8: technology-not-marketing + human science-pop

- Hard editorial gate rejects product marketing, preorder/sales/price/trim/availability stories when there is no meaningful technological novelty.
- Consumer products are publishable only when there is a concrete engineering/technology advance (control system, powertrain, battery, autonomy, sensors, chips/process, manufacturing, materials, communications, safety, etc.).
- Marketing-heavy sources with a real technical development are stripped down to the technical substance.
- Ukrainian rewrite style is now explicitly science-pop for an intelligent non-specialist: explain jargon at first use, restructure the source, use natural Ukrainian syntax and short readable paragraphs, avoid literal translation and press-release language.
- The AI output now self-classifies editorial type and states the novelty reason before publication; marketing/opinion-classified output cannot pass the publish validator.
- Existing `Data` from RC7 remains compatible.

Окремий автономний Windows portable продукт для кількох Telegram-каналів.

## Що виправлено в RC4

- Форма каналу більше не підставляє жодну назву: назву вводить користувач.
- Поле редакційного опису/профілю прибрано з форми каналу. Внутрішній технологічний профіль застосовується автоматично.
- Цільовий Telegram-канал можна вказати як `https://t.me/username`, `@username`, простий `username` або числовий Chat ID.
- Посилання `t.me/...` автоматично нормалізується до `@username`, який приймає Telegram Bot API.
- Ctrl+V і Shift+Insert тепер вставляють текст прямо з Windows clipboard, без залежності від стандартної Tk virtual-paste події.
- Контекстне меню правої кнопки використовує той самий прямий механізм вставки.

## Бойовий формат публікації

Для кожної нової релевантної англомовної новини програма без ручного погодження:

1. перевіряє точний та семантичний дубль у межах конкретного цільового каналу;
2. створює сильний український заголовок;
3. створює повний український редакційний рерайт для Telegraph;
4. витягує доступні медіа;
5. створює Telegraph-сторінку: заголовок + повний матеріал + медіа + посилання на першоджерело;
6. створює Telegram-анонс до 900 символів;
7. публікує в Telegram одне перевірене головне редакційне фото (якщо воно є), а під ним анонс і посилання `Читати повністю: <Telegraph URL>`;
8. записує Telegraph URL, Telegram message ID, кількість медіа та результат у локальну базу.

## Мультиканальність

Кожен цільовий Telegram-канал має власні джерела, історію, дедуплікацію та часові правила. Внутрішній технологічний відбір застосовується автоматично. Джерелами можуть бути RSS/Atom, вебсайти та публічні Telegram-канали.

Нове джерело спочатку проходить baseline, тому старий архів не публікується після додавання.

## AI Router

Cloud provider chain with bounded failover and installed Ollama as the last local fallback. Existing loopback llama.cpp remains a manual emergency fallback.

## Дані і секрети

- `Data/telegram_autopilot.sqlite3` — локальна база;
- `Data/secrets.secure` + `Data/secrets.key` — зашифровані токени;
- Telegraph token також зберігається локально;
- `Data` цього продукту не використовується UA FREE Content Tool.

## RC7: structured article media

- Article media is no longer collected as a flat bag and sprinkled through Telegraph.
- The extractor preserves source order as text / figure / caption blocks.
- AI keeps explicit media markers at the same narrative points in the Ukrainian rewrite.
- Telegraph places validated editorial media at those markers and uses Ukrainian AI captions when available.
- `og:image` is reserved as the Telegram hero/fallback and is not duplicated above the same inline article image.
- Images are downloaded and validated before publication; tiny placeholders, banner shapes and byte-identical duplicates are removed.
- Telegram uploads one validated editorial hero as file bytes, avoiding publisher CDN hotlink blocks.
- RC6 `Data` is migrated in place with additive SQLite columns; channels, sources, baselines, history and tokens remain intact.

## RC6

### RC6: editorial media sanitation
- Filters advertising, sponsored, affiliate, promo, recommendation and newsletter containers before text reaches AI.
- Filters obvious display-ad media by DOM context, URL markers, alt text and banner aspect ratio.
- Prefers featured/figure/article media from the actual article page over images embedded in RSS descriptions.
- Prefers semantically marked article/main text over surrounding navigation and page chrome.
- Keeps Data/database/secrets format unchanged and compatible with RC5.

- Джерела RSS/Atom і вебсторінки запитуються з browser-like HTTP headers, щоб публічні feeds на CDN/WAF не відхиляли bare-library User-Agent.
- HTTP 403 повторюється один раз з навігаційним профілем заголовків.
- Помилка 403 тепер окремо пояснює, що сервер відхилив автоматичний запит, а не що URL нібито неправильний.
- Формат `Data`, база, канали, джерела, baseline, історія та зашифровані токени не змінювалися. Папку `Data` з RC4 можна переносити цілком.

## Development policy

`main` залишається мінімальною стабільною точкою репозиторію. RC9 живе у `develop/rc9-foundation` і не промотується до живої перевірки на Windows із реальною `Data`.

Для GitHub-редагувань цього проєкту використовуються only whole-file Contents API operations. Blob/tree/chunk patching не використовується.
