# UA FREE Telegram Autopilot v2.0.0-rc90

Ювілейний stabilization release після live-перевірки RC89.

## Виправлено

- Credential recovery більше не зупиняється лише тому, що Codex уже налаштований. Поточні непорожні secrets завжди мають пріоритет, а відсутні Gemini/NVIDIA/Groq/Cloudflare/Local та службові credentials можуть безпечно дозаповнюватися з валідних старих Autopilot Data.
- Recovery може зібрати відсутні поля з кількох валідних sibling Data, не перезаписуючи актуальні значення.
- First-run import більше не копіює стару encrypted secret pair поверх нової: credentials об'єднуються по відсутніх полях, тому вже встановлений Codex/поточні значення не затираються.
- 15-хвилинний polling baseline тепер застосовується після того, як імпортовані канали реально існують. Порожня схема більше не «з'їдає» migration marker RC90.
- Уже імпортовані RC89 бази з 5-хвилинним polling отримують одноразове виправлення; після цього ручні зміни оператора зберігаються.
- Source/runtime Codex dependency вирівняно з фактичним bootstrap runtime: `openai-codex==0.156.1`.

## Збережено без змін

- anti-slop;
- source-specific text-only cleanup;
- cross-source semantic/event dedupe;
- incident clustering;
- editorial review/learning;
- exact-post Telegram media ownership;
- signed remote updater;
- усі channel/source settings та історія.
