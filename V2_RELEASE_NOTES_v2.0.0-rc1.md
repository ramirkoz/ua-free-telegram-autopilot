# UA FREE Telegram Autopilot V2 2.0.0-rc1

> **Superseded by 2.0.0-rc2.** RC1 має Windows-баг міграції старої Data: спроба файлового `os.replace()` живої SQLite може дати WinError 32. Для імпорту старої Data використовувати RC2 або новішу версію.

Перший Windows preview чистого V2 runtime.

## Що змінено

- V2 запускається окремим entrypoint і не виконує історичний стек `rcXX` monkey-patches.
- Durable queue з явними етапами, рішеннями, блокерами, lease та recovery після перезапуску.
- Єдиний AI health registry для worker, scheduler та UI. Технічна відмова AI переводить матеріал у очікування, а не в редакційне відхилення.
- Fresh-first та ізоляція каналів: проблема одного каналу не повинна зупиняти інші.
- Строгіший dedupe конкретної події та підтримка donor media без масового склеювання схожих тем.
- Monitoring застосовує лише збережені inclusion/exclusion rules і не робить fail-open при недоступному AI.
- Canonical source URL є обов'язковим publication gate; footer `Джерело` додає publisher.
- Окрема read-only міграція старої Data: канали, джерела, політики, editorial settings, published history, dedupe/feedback та encrypted credentials. Runtime cooldown/retry/worker state не переносяться.
- Український V2 UI з окремими екранами черги, історії, AI health, міграції та журналів.
