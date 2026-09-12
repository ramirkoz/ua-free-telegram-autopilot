> Current portable: **v2.0.0-rc18**

RC18 fixes Telegram media extraction: channel avatars/logos, author photos, reactions, link-preview chrome and video thumbnail/posters are filtered before MediaBundle using the full HTML ancestor stack. Telegram re-ingest now replaces the source media snapshot instead of merging old contaminated URLs; pre-RC18 pending Telegram rows are quarantined until a clean refresh. TTL expiration now parses RFC2822 source dates in Python, so stale jobs do not survive beyond `max_age_hours` merely because SQLite cannot parse their timestamp.

# UA FREE Telegram Autopilot V2 2.0.0-rc18

Windows portable застосунок для багатоканального збору новин, редакційного відбору, AI-рерайту та автоматичної публікації в Telegram.

RC17 fixes live publication transport: Autopilot now downloads source media itself and uploads local bytes to Telegram instead of giving Bot API third-party URLs that can fail with `WEBPAGE_CURL_FAILED`. Publication retries now have durable backoff, Supervisor media-loss accounting uses the actual deduplicated publication bundle, RFC 2822 source dates are parsed correctly, and `recent_events.json` is populated directly from operational logs when the audit table is sparse.

## Поточна архітектура

V2 є чистим runtime без активного історичного `rcXX` patch stack. Старі RC-файли можуть залишатися в репозиторії лише як історичні regression fixtures, але V2 їх не імпортує і Windows Portable їх не містить.

Основні модулі V2:

- `telegram_autopilot/v2/storage.py` — SQLite schema, durable jobs, stage/decision/blocked_by.
- `telegram_autopilot/v2/ingest.py` — збір і нормалізація джерел, Telegram stitching.
- `telegram_autopilot/v2/dedupe.py` — strict exact/event dedupe і donor media.
- `telegram_autopilot/v2/editorial.py` — selector, monitoring policy, writer, QA.
- `telegram_autopilot/v2/ai_gateway.py` — єдиний AI router/health registry.
- `telegram_autopilot/v2/runtime.py` — fresh-first scheduler, per-channel isolation, recovery.
- `telegram_autopilot/v2/media_pipeline.py` — media contract: validation, source-order bundle, canonical duplicate collapse, multiple media + caption delivery.
- `telegram_autopilot/v2/publisher.py` — publication gate і Telegram transport.
- `telegram_autopilot/v2/migration.py` + `migration_service.py` — read-only import старої Data.
- `telegram_autopilot/v2/loghub.py` — окремі журнали за підсистемами.
- `telegram_autopilot/v2/ui.py` — операторський інтерфейс.

## Ключові інваріанти

- AI/provider outage не є редакційною відмовою.
- `WAITING_AI` автоматично прокидається після відновлення здорового провайдера.
- Свіжі матеріали мають пріоритет над старим backlog.
- Один проблемний канал не блокує інші.
- Monitoring використовує збережені inclusion/exclusion rules і не робить fail-open при недоступному AI.
- Без canonical source URL матеріал не може стати `READY` або `PUBLISHED`.
- Посилання всередині первинного повідомлення не підміняє джерело самої новини.
- Publication pacing не обходиться режимом «публікувати одразу».
- Невизначений результат Telegram write не ретраїться всліпу, щоб не створювати дубль.

## AI

V2 використовує один health registry для router, workers, scheduler та UI.

Підтримуються Codex/ChatGPT, Google Gemini, NVIDIA NIM, Groq, Cloudflare та локальний OpenAI-compatible резерв.

V2 portable зберігає Codex 0.147.0 частиною самого Windows Portable runtime. Тобто нова V2-папка більше не залежить від `Data/ai_runtime` старої RC82 або від випадково встановленого SDK у сусідній програмі. Авторизація використовує ChatGPT account користувача. Codex не має hardcoded `gpt-5.x`: використовується account-default/доступна модель акаунта.

Тимчасові network/quota/timeout помилки відокремлені від permanent auth/model/config errors. Після відновлення здорового провайдера AI-blocked jobs повертаються в робочу чергу без витрачання editorial retry budget.

## Міграція зі старого Autopilot

Не копіюйте стару `Data` поверх V2 вручну.

1. Розпакуйте V2 в нову папку.
2. Запустіть `UA_FREE_Telegram_Autopilot.exe`.
3. Відкрийте `Міграція` → `Імпортувати стару Data`.
4. Виберіть `Data` робочої legacy-версії, рекомендована база для переходу — RC82.

Legacy SQLite відкривається тільки read-only. Перед заміною V2 БД створюється backup.

Переносяться канали та Telegram targets, джерела, ChannelPolicy, inclusion/exclusion, prompts, editorial weights, language/media/publication settings, published/dedupe history, feedback та зашифрована пара `secrets.key + secrets.secure` без розшифрування.

Не переносяться transient runtime state: старі provider cooldown, retry timers, worker state, circuit state, RC markers та технічні transient errors.

Міграція використовує Windows-safe SQLite online backup API та окремі унікальні temp-файли для `secrets.key` і `secrets.secure`.

## Дані та логи

Portable дані зберігаються у `Data` поруч із програмою.

- V2 database: `Data/telegram_autopilot_v2.sqlite3`
- Migration backups: `Data/migration_backups/`
- Логи: `Data/logs/v2/`

Логи розділені за підсистемами, щоб AI, ingest, editorial, worker, publication та migration не зливалися в один нескінченний файл.

## Запуск із source

```bash
python app_v2.py
```

Потрібен Python 3.11+ та залежності з `requirements.txt`.

## Реліз

Поточний release line: `v2.0.0-rc18`.

Windows Portable будується на GitHub Actions під Windows і перед публікацією проходить full regression suite, clean-V2 gate, перевірку вбудованого Codex SDK, native GUI startup, credential-pair migration smoke та Microsoft Defender scan. Точні SHA256 публікуються разом із release assets у `UA_FREE_Telegram_Autopilot_v2.0.0-rc18_SHA256SUMS.txt`.

Legacy RC82 зберігається як rollback baseline, але не є поточною mainline-архітектурою.

## Нагляд / Supervisor

V2 містить окремий модуль `telegram_autopilot.v2.supervisor`, який не приймає редакційних рішень і не перезапускає систему самовільно. Він кожні 15–600 секунд формує `Data/supervisor/status.json`, перевіряє worker heartbeat, AI health, активну чергу, SQLite `quick_check`, масові помилки джерел і вільне місце на диску.

У вкладці **Нагляд** можна:

- обрати локальну папку Google Drive Desktop для прямого file feed;
- дзеркалити `status.json`, `incident.json`, `recent_events.json` і diagnostic ZIP;
- вручну оновити feed або створити diagnostic ZIP.

Окремий Telegram-бот оповіщень і окремий analysis agent прибрані. При новому WARNING/CRITICAL Supervisor один раз створює diagnostic ZIP, а далі постійно оновлює файловий feed, який можна читати напряму. Diagnostic bundle не містить `secrets.key`, `secrets.secure`, API keys або повну SQLite базу; хвости логів проходять redaction. Навмисний **Стоп** не класифікується як аварія.

V2 також містить виправлення кнопок **Редагувати канал** і **Джерела**: вибір рядка більше не губиться під час автоматичного refresh, перший рядок вибирається автоматично, підтримуються double-click і Enter.


## RC17: локальний Telegram upload і publication backoff

RC17 прибирає головну причину `WEBPAGE_CURL_FAILED`: Autopilot сам завантажує кожне source media, перевіряє тип/розмір, дедуплікує точні binary clones і передає Telegram multipart upload. Для media group використовуються `attach://...` файли, тому Telegram більше не повинен сам CURL-ити CDN/сайт джерела.

Publication transport має власний durable backoff. READY-матеріал із Telegram/media failure не ретраїться по кілька разів на секунду: retryable errors отримують `next_retry_at`, permanent failures чекають refresh/оператора, а unknown Telegram outcome взагалі не повторюється автоматично через ризик дубля. При першому запуску RC17 вузька startup-maintenance розблоковує READY-матеріали, які RC16 залишив на `WEBPAGE_CURL_FAILED`, щоб вони одразу пройшли через новий local-upload transport.

Supervisor у RC17 порівнює `telegram_media_count` з фактичним expected publication count, а не сирою кількістю URL/declared media. RFC 2822 дати RSS (`Fri, 11 Sep 2026 ...`) враховуються у `oldest_due_age`. `recent_events.json` тепер підтягує структуровані хвости реальних V2 логів, якщо `audit_events` порожній, тому прямий Drive feed корисний без alert-бота та analysis agent.


## RC7: throughput та порядок публікації

RC7 виправляє кореневу причину нічного backlog: у RC6 poll interval відраховувався від початку довгого collection cycle. Якщо збір тривав довше за інтервал, worker одразу запускав новий повний збір і встигав обробити лише один job між циклами. RC7 відраховує poll interval від завершення збору, тому між collection cycles worker реально розгрібає чергу.

Supervisor v2 використовує реальну job-активність усіх станів, а не лише timestamp активних jobs; додає startup grace, throughput/age метрики та стани HEALTHY/DEGRADED/STALLED/DEAD. Низький throughput відділений від справжнього stall.

Налаштування `max_age_hours` тепер реально виконується: старі PENDING jobs архівуються як `STALE_MAX_AGE`, не забиваючи чергу безкінечно. READY/PUBLISHED матеріали цим cleanup не зачіпаються.

Telegram-публікація з медіа використовує **caption до 900 символів**: 1 медіа → 1 photo/video post з caption; 2–10 різних медіа → Telegram media group з caption; понад 10 → кілька груп, caption на фінальній групі. Одна й та сама картинка в різних size/cache URL не множиться в галереї. Політика `required / preferred / optional` задається оператором у налаштуваннях каналу, без hardcode для конкретних каналів. Telegram-джерела можуть мати media-only і text-only повідомлення підряд: V2 консервативно stitch-ить суміжну пару в одну логічну публікацію.

## RC18: чисте Telegram media extraction

RC18 відсікає Telegram UI chrome до формування MediaBundle: аватар/логотип каналу, author/user photo, reaction/emoji, link-preview image та `video_thumb` не стають вкладеннями публікації. Для відео використовується реальний `<video>/<source>` URL; poster не публікується як окрема фотографія.

Повторний Telegram ingest тепер замінює source media snapshot, а не merge-ить його зі старим `media_json`. Одноразова startup-maintenance очищає непубліковані pre-RC18 Telegram snapshots і не дає їм пройти далі, доки джерело не буде перечитане новим фільтром. Supervisor показує telemetry `raw_candidates / discarded_non_content / discarded_video_thumb / discarded_duplicate / content_media`.

TTL cleanup переведений на Python-парсинг ISO/RFC2822 дат і нормалізує legacy timestamp у ISO, тому старі QUEUED/WAITING матеріали реально архівуються за `max_age_hours`.
