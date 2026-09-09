# UA FREE Telegram Autopilot V2 2.0.0-rc4

RC4 виправляє головний runtime-дефект RC3, знайдений після успішної реальної міграції RC82 → V2: програма переносила encrypted API/Telegram credentials, але новий portable не містив Codex SDK, на який фактично спирався стабільний старий Autopilot і Content Tool.

## Виправлено

- `openai-codex==0.147.0` тепер входить до залежностей і фізично пакується всередину Windows Portable.
- Нова V2-папка більше не залежить від старого `Data/ai_runtime` RC82 для наявності Codex SDK.
- Release pipeline перевіряє `openai_codex` уже всередині готового portable та вимагає `inspect_codex().installed == True`.
- Codex як і раніше не має hardcoded GPT-моделі: використовуються account-default/моделі, доступні ChatGPT-акаунту.
- Головний екран більше не рахує всі імпортовані archived/PENDING записи як активні «блокери». Блокери рахуються лише для живих jobs у QUEUED/WAITING/LEASED.
- Головний екран показує реальну кількість editorial reject та configured/healthy AI замість декоративного `0/6` без контексту.
- CI live-source gate більше не валить реліз через одиничний зовнішній HTTP 403: перевіряється кілька підтримуваних джерел і потрібен хоча б один реальний успішний збір; індивідуальні anti-bot відмови логуються як warning.
- Drive exact-assets workflow запускається тільки після успішного release workflow, а не змагається з ним на одному push.

## Збережено з RC3

- read-only legacy import;
- Windows-safe SQLite online backup migration;
- окремі temp-файли для `secrets.key` і `secrets.secure`;
- source URL як жорсткий publication gate;
- explicit monitoring policy;
- durable fresh-first queue;
- per-channel worker isolation;
- AI outage → WAITING_AI, а не editorial reject;
- automatic wake-up AI-blocked jobs після відновлення провайдера;
- чистий V2 runtime без активного `rcXX` patch stack.

## Перевірки перед публікацією

GitHub Windows release workflow повинен пройти full regression suite, Windows migration regressions, clean-V2 contract, bundled Codex package gate, native packaged GUI startup, credential-pair migration smoke, Authenticode validation та Microsoft Defender scan для runtime і ZIP.
