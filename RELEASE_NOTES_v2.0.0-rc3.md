# UA FREE Telegram Autopilot V2 2.0.0-rc3

RC3 є поточною clean-V2 збіркою після реальної міграції робочої RC82 Data.

## Виправлено

- Windows migration більше не замінює живу SQLite через `os.replace`; використовується SQLite online backup API.
- `secrets.key` і `secrets.secure` мають окремі унікальні temp-файли і переносяться як точна зашифрована пара.
- Збій переносу credentials не відкочує вже успішно перенесені канали, джерела, policy та history.
- Доданий native Windows credential-pair migration smoke з byte-for-byte перевіркою.

## V2 runtime

- Чисті модулі без активного `rcXX` monkey-patch stack.
- Durable queue зі `stage / decision / blocked_by`.
- Fresh-first scheduling та ізоляція каналів.
- Єдиний AI health registry та автоматичне wake-up `WAITING_AI`.
- Provider outage не стає editorial reject.
- Codex використовує account-default модель, без hardcoded `gpt-5.x`.
- Monitoring використовує збережені inclusion/exclusion rules і fail-closed при недоступному AI.
- Canonical source URL є жорстким publication gate.
- Strict dedupe, Telegram stitching, donor media та per-channel media policy збережені.

## Перевірка релізу

Windows release pipeline перевіряє повний regression suite, clean-V2 source/import contract, native GUI startup, native credential migration і Microsoft Defender scan розпакованої програми та ZIP.

## Міграція

Розпакуйте RC3 у нову папку, запустіть `UA_FREE_Telegram_Autopilot.exe`, відкрийте `Міграція` → `Імпортувати стару Data` і виберіть Data робочої RC82.
