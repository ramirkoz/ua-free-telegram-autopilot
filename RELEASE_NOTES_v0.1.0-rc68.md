# UA FREE Telegram Autopilot v0.1.0-rc68

RC68 переносить перевірку «чи вартий матеріал окремої публікації для живої людини» з логіки окремих каналів у системне ядро автопілота і чітко розділяє редакційний та моніторинговий режими.

## Що змінилося

- **Universal Editorial Value Gate.** Усі канали з `channel_mode=editorial` після перевірки відповідності власній CHANNEL POLICY проходять однаковий системний gate, незалежний від назви, тематики чи бренду каналу.
- Gate окремо оцінює `novelty`, `consequence_or_insight`, `mechanism`, `reader_payoff`, `retellability`, `concrete_stakes`, `why_now` і прапорець `curiosity_only`.
- Екзотична тема, великі числа, красива картинка, знаменитість або гіпотетичне «уявіть» самі по собі більше не є достатньою причиною для редакційної публікації.
- Сильна наука не карається за відсутність утилітарної користі: нове відкриття, сильний механізм або нове розуміння можуть пройти через `consequence_or_insight` / `mechanism`.
- **Channel fit і Editorial Value розділені.** Channel-fit selector перевіряє тільки відповідність політиці конкретного каналу і прямо заборонений оцінювати broad appeal; Editorial Value Gate працює окремо під капотом.
- **Monitoring bypass.** Канали з `channel_mode=monitoring` повністю обходять Editorial Value Gate, human-interest/broad-appeal оцінки, реакційне тематичне приглушення, добовий тематичний баланс і spacing близьких історій.
- Для monitoring зберігаються dedupe / merge / update, multi-source clusters, writer/Fact Guard/structural QA і швидкий READY-first runtime RC67.
- **Monitoring exclusions.** Якщо в політиці каналу явно задані власні `rejection_rules`, вони використовуються тільки як exclusion rules. Матеріал за замовчуванням проходить; якщо exclusion AI недоступний, monitoring працює fail-open, щоб не пропускати новини через збій оцінювача.
- Якщо `rejection_rules` лишилися стандартними, monitoring не запускає зайвий AI selector взагалі.
- Для monitoring прибрано editorial-diversity переупорядкування pending-черги: нові матеріали йдуть у природному новинному порядку, а dedupe/cluster виконується just-in-time як у RC67.
- Результат Editorial Value Gate зберігається в SQLite (`editorial_value_score`, JSON діагностика, reason, timestamp), щоб retry не ганяв ту саму історію через gate без потреби і щоб рішення можна було аналізувати в логах/базі.

## Сумісність

- Існуюча `Data` з RC67/RC66/RC65 зберігається.
- Міграція лише додає діагностичні колонки через `ALTER TABLE`-сумісний механізм; destructive reset відсутній.
- Налаштування `Редакційний / Моніторинговий`, READY-пул, розклад публікації, `Одразу`, кластеризація, тематичний баланс редакційних каналів і structural gate RC66/RC67 збережені.

## Regression coverage

RC68 додає тести для:
- відхилення curiosity-only матеріалу без reader payoff;
- проходження історії з новим ресурсом/механізмом/наслідком;
- обов'язкового запуску Universal Editorial Value Gate для editorial mode;
- повного обходу цього gate у monitoring mode;
- відсутності topic balance / related spacing у monitoring;
- нейтрального reaction-feedback suppression у monitoring;
- збереження старого editorial pending ordering для editorial mode.
