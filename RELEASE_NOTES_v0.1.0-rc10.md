# UA FREE Telegram Autopilot v0.1.0-rc10

RC10 є контрольованим наступником RC9. Він навмисно **не переписує перевірений publishing path**. Зміни додаються перед Telegram-write та в локальну діагностику.

## Що додано

### Evidence Pack

Замість механічного обрізання довгої статті програма локально, без додаткового AI-запиту, формує bounded Evidence Pack:

- заголовок і дата джерела;
- лід;
- речення з числами й одиницями;
- назви продуктів/компаній/моделей;
- attribution/uncertainty;
- high-risk claims типу first/largest/record.

Порядок відібраних речень зберігається. Це зменшує ризик, що важливий факт у другій половині матеріалу не потрапить у prompt.

### Fact Guard

Після чинних RC9 перевірок мови, довжини, завершеності, років, чисел і термінології додано консервативний article-aware guard. Він блокує:

- латинську назву/модель, якої немає у source;
- «перший/вперше» без source-сигналу first;
- «найбільший» без largest/biggest;
- «найшвидший» без fastest;
- «найпотужніший» без most powerful;
- «рекорд» без record.

Guard навмисно вузький: він не намагається замінити LLM другим LLM і не додає API-викликів.

### Source Health

Для кожного джерела локально накопичуються:

- last success;
- last new item;
- скільки матеріалів додано останньою перевіркою;
- загальна кількість перевірок;
- загальна кількість помилок;
- загальна кількість отриманих матеріалів.

Нові таблиці створюються через `CREATE TABLE IF NOT EXISTS`; старі `channels`, `sources`, `articles`, `Data` та secret format не переписуються.

### Persisted Audit Trail

Локальна БД зберігає ключові етапи:

`collect → gate/dedupe → rewrite → telegram_writing → published/error`.

Observability fail-open: якщо запис журналу не вдався, це не блокує production processing. Bot token, query token/key та Bearer values маскуються перед записом.

## Що спеціально НЕ змінено

- `new` має пріоритет над `retry`;
- retry backoff та max attempts;
- cycle deadline;
- точна дедуплікація;
- Media Engine RC9;
- 900 символів із медіа / 4096 без медіа;
- fallback «Telegram відхилив фото → той самий пост без фото»;
- `unknown` не запускає сліпий повтор;
- AI Router priority/failover;
- Codex не використовується у production rewrite;
- існуюча Ollama використовується як останній local fallback без перевстановлення та без автоматичного pull моделей;
- формат AES-GCM secret storage.

## Сумісність Data

RC10 додає лише нові службові таблиці `source_health` і `audit_log`. Існуючі записи не видаляються й не переносяться.

`POST_FORMAT_PREFIX` піднято з `telegram-post-v4` до `telegram-post-v5`, тому **ще не опубліковані** RC9-кандидати при наступній обробці проходять новий Evidence Pack + Fact Guard. Вже опубліковані матеріали не перепубліковуються.

## Установка

Додатково встановлювати нічого не потрібно. RC10 використовує той самий portable runtime та ті самі зовнішні залежності, що RC9.

## Acceptance status

- Local regression and compatibility gate: PASS.
- User/operator live smoke on the real Windows working environment and existing `Data`: PASS on 2026-08-18 (reported as working, with no regression raised before synchronization).
- This is a controlled smoke acceptance, not a claim that every external API edge case was exhaustively exercised.
- Merge to `main` remains conditional on green GitHub CI for the exact synchronized source tree.
