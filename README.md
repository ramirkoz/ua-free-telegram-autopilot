# UA FREE Telegram Autopilot v0.1.0-rc41

Windows portable застосунок для збору технологічних/наукових новин, редакційного відбору, безпечного AI-рерайту українською та прямої публікації в Telegram.

## Production-конвеєр RC41

`джерело → source-health/backoff → exact/event dedupe → newsworthiness → RC41 editorial mix → media relevance → Evidence Pack → RU editorial bridge (optional fallback) → fresh UA author → hard Fact Guard/UA safety → soft quality repair → Telegram`

### RC41: редакційний баланс стрічки

- Редакційні теми розділені на окремі групи: AI/моделі/агенти, practical/open source, робототехніка/мобільність, наука/медицина/енергетика, космос, hardware/compute, consumer tech, tech business/platforms та cyber.
- Cybersecurity більше не отримує автоматичний bypass лише через `CVE-*` або формулювання `critical vulnerability`. Звичайні advisory проходять той самий rolling balance, що й інші теми.
- Для cyber діє найжорсткіший ліміт повторів: третій security-слот у останніх десяти або другий у короткому чотирипостовому відрізку відсувається на користь іншої сильної історії. Справді масові emergency/zero-day події можуть пройти поза цим обмеженням.
- AI лишається базовою тематикою CTRL+UA і має більше редакційного простору, але practical tools, robotics, science та consumer tech більше не губляться всередині широких категорій.
- RC37 newsworthiness збережений. Водночас справді корисні open-source інструменти, бібліотеки, фреймворки, курси та репозиторії можуть пройти, навіть якщо оригінальний заголовок оформлений як guide/explainer. Shopping/deals/accessory roundups не рятуються.
- Список джерел не зашитий у реліз: його як і раніше керує оператор через Sources UI, щоб змінювати пріоритети без нового білду.

### Редакторський міст RC40, збережений у RC41

- Перший AI-прохід пише внутрішню російську редакторську чернетку і шукає сильний факт, конфлікт, наслідок, дивну деталь або людський епізод.
- Російська чернетка не є джерелом фактів. Якщо bridge і SOURCE суперечать один одному, SOURCE має абсолютний пріоритет.
- Другий прохід пише український пост заново; буквальний переклад речення за реченням заборонений.
- Якщо bridge-провайдери недоступні, фінальний автор може працювати безпосередньо з SOURCE.

### Стиль і safety

- Немає фіксованої кількості слів, речень або абзаців.
- Для поста з фото лишається hard limit 900 символів; довжина не добивається водою.
- Факти, нові числа/сутності, обірваний текст, ненормативна українська та структурна корупція залишаються hard blockers.
- Safe-кандидат із неідеальним стилем може отримати один targeted copy-edit repair; невдалий repair не вбиває безпечний оригінал.
- Evidence Pack, Fact Guard, number/year checks, attribution/relationship protections, Ukrainian hard gate та media-required publishing залишаються обов’язковими.
- Cache marker: `telegram-post-v26`, тому pending/retry старих drafts перегенеровуються через RC41 policy.

## AI Router

- RU bridge спочатку пробує Gemini/Groq/NVIDIA/Cloudflare/local без Codex.
- Якщо альтернативні провайдери недоступні, bridge може перейти на Codex/Gemini або бути пропущений.
- Фінальний український автор: `Codex / ChatGPT → Gemini`, а при їх недоступності `Groq → NVIDIA` під тим самим hard Fact Guard.

## Медіа

- Без релевантного фото/відео новина не публікується (`SKIP_NO_MEDIA`).
- Featured/OG image потребує story-specific semantic evidence.
- Якщо Telegram відхиляє медіа, текстовий fallback заборонений.

## Дані та portable-режим

SQLite-схема не змінена. Для оновлення розпакуйте RC41 у нову папку та перенесіть туди **всю папку `Data`** з RC40. Не накладайте runtime-файли поверх старої збірки.
