# UA FREE Telegram Autopilot v2.0.0-rc29

## Що виправлено

- Telegram більше не повинен перетворювати CVE-ідентифікатори та dotted build/version numbers на фальшиві телефонні посилання: Autopilot передає їх як явні `code` entities без zero-width символів і без зміни копійованого тексту.
- Реальні телефонні номери не форматуються як `code` і зберігають стандартну поведінку Telegram.
- Production Telegram parser отримав media-filter v5: семантичні photo/video/media/album/grouped wrappers переживають зміну CSS-класів Telegram.
- Якщо точний `data-post` не має прямого attachment, але має власну link-preview image, використовується одна exact-post preview image як fallback. Це не позичає медіа з сусідніх Telegram-постів.
- Пряме фото/відео завжди має пріоритет над link-preview fallback. Avatar/reaction/reply/logo/promo/video-thumb як і раніше відсікаються.
- CI отримав живий Telegram media gate на кількох публічних запорізьких каналах, щоб реліз не проходив, якщо production parser знову бачить пости, але не бачить жодного медіа.

## Сумісність

- Формат `Data` і SQLite schema не змінюються.
- Існуючий `Data\ai_runtime` з Codex перевикористовується.
- RC27/RC28 startup/file-lock hardening збережено.
- Для переходу з RC28: закрити програму, розпакувати RC29 у нову папку, скопіювати всю стару `Data` до RC29 до першого запуску.
