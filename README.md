# UA FREE Telegram Autopilot V2 2.0.0-rc3

Windows portable застосунок для багатоканального збору новин, редакційного відбору, AI-рерайту та автоматичної публікації в Telegram.

## Поточна архітектура

V2 є чистим runtime без активного історичного `rcXX` patch stack. Старі RC-файли можуть залишатися в репозиторії лише як історичні regression fixtures, але V2 їх не імпортує і Windows Portable їх не містить.

Основні модулі V2:

- `telegram_autopilot/v2/storage.py` — SQLite schema, durable jobs, stage/decision/blocked_by.
- `telegram_autopilot/v2/ingest.py` — збір і нормалізація джерел, Telegram stitching.
- `telegram_autopilot/v2/dedupe.py` — strict exact/event dedupe і donor media.
- `telegram_autopilot/v2/editorial.py` — selector, monitoring policy, writer, QA.
- `telegram_autopilot/v2/ai_gateway.py` — єдиний AI router/health registry.
- `telegram_autopilot/v2/runtime.py` — fresh-first scheduler, per-channel isolation, recovery.
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

Codex не має hardcoded `gpt-5.x`: використовується account-default/доступна модель акаунта. Тимчасові network/quota/timeout помилки відокремлені від permanent auth/model/config errors.

## Міграція зі старого Autopilot

Не копіюйте стару `Data` поверх V2 вручну.

1. Розпакуйте V2 в нову папку.
2. Запустіть `UA_FREE_Telegram_Autopilot.exe`.
3. Відкрийте `Міграція` → `Імпортувати стару Data`.
4. Виберіть `Data` робочої legacy-версії, рекомендована база для переходу — RC82.

Legacy SQLite відкривається тільки read-only. Перед заміною V2 БД створюється backup.

Переносяться:

- канали та Telegram targets;
- джерела;
- ChannelPolicy, inclusion/exclusion, prompts, editorial weights;
- language/media/publication settings;
- published history та dedupe history;
- feedback/learning data;
- зашифрована пара `secrets.key + secrets.secure` без розшифрування.

Не переносяться transient runtime state: старі provider cooldown, retry timers, worker state, circuit state, RC markers та технічні transient errors.

RC3 містить Windows-safe SQLite migration через online backup API та окремі унікальні temp-файли для `secrets.key` і `secrets.secure`.

## Дані та логи

Portable дані зберігаються у `Data` поруч із програмою.

V2 database:

`Data/telegram_autopilot_v2.sqlite3`

Migration backups:

`Data/migration_backups/`

Логи:

`Data/logs/v2/`

Логи розділені за підсистемами, щоб AI, ingest, editorial, worker, publication та migration не зливалися в один нескінченний файл.

## Запуск із source

```bash
python app_v2.py
```

Потрібен Python 3.11+ та залежності з `requirements.txt`.

## Реліз

Поточний реліз: `v2.0.0-rc3`.

Windows Portable будується на GitHub Actions під Windows, проходить regression tests, clean-V2 import gate, native GUI startup, credential-pair migration smoke та Microsoft Defender scan.

SHA256 поточного Windows Portable:

`a3c5ed24bc6fcd4584222abba87d11d42ea82eafda6c4785d59eb5e090d844ac`

Legacy RC82 зберігається як rollback baseline, але не є поточною mainline-архітектурою.
