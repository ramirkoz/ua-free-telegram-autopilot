# UA FREE Telegram Autopilot v0.1.0-rc37

Windows portable застосунок для збору технологічних/наукових новин, редакційного відбору, безпечного AI-рерайту українською та прямої публікації в Telegram.

## Production-конвеєр RC37

`джерело → source-health/backoff → exact/event dedupe → newsworthiness gate → media relevance gate → Evidence Pack → trusted writer → Fact Guard → mandatory human-interest editor → final UA/editorial gates → Telegram`

### Редакційний відбір

- Автопілот не повинен займати слот гайдами, explainers, shopping/accessory roundups, порадами, колонками, poetry/soft conference recaps та іншими матеріалами без окремої новинної події.
- Очевидні multi-topic editorial mashups відсіюються до AI-рерайту.
- Високий priority джерела не дає автоматичного пропуску слабкому конкретному матеріалу.

### Стиль CTRL+UA

- Writer шукає не «весь зміст статті», а найцікавішу історію всередині неї.
- Перше речення має бути фактичним гачком: наслідок, конфлікт, сильна цифра, несподівана деталь або конкретна зміна.
- У фінальний пост беруться лише 3–6 деталей, які реально варто запам'ятати.
- Немає обов'язкової чотириабзацної структури, формального висновку, пояснення очевидного та AI-переходів на кшталт «це важливо, тому що».
- Додані topic-near synthetic few-shot examples. Вони навчають редакторської механіки, але їхні факти заборонено переносити в поточну новину; Fact Guard це додатково перевіряє.
- Final human-interest editor є обов'язковим. Якщо Codex/Gemini не можуть дати живий і фактологічно безпечний текст, матеріал іде в bounded retry, а не публікує нудний safe draft.

### AI Router

- Unattended production writer/editor: `Codex / ChatGPT → Gemini`.
- NVIDIA, Groq, Cloudflare та local Ollama/llama.cpp залишаються доступними в діагностиці/LAB, але production більше не витрачає хвилини на fallback-ланцюжок, який усе одно потребував Codex/Gemini перед публікацією.
- Provider health/cooldown і article QA залишаються розділеними.

### Медіа

- Без релевантного фото/відео новина не публікується (`SKIP_NO_MEDIA`).
- Featured/OG image не вважається релевантним лише через metadata: потрібен story-specific semantic evidence.
- Якщо Telegram відхиляє медіа, текстовий fallback заборонений.

### Source health

- Хронічні HTTP 429/403, HTML замість feed, network/DNS/timeout помилки отримують persistent adaptive backoff.
- Чим довше джерело стабільно помиляється, тим довша пауза; успішна перевірка очищає `last_error` і одразу повертає нормальний цикл.
- Ручний `Перевірити зараз` свідомо обходить backoff.

### Safety

- Evidence Pack, Fact Guard, number/year checks, attribution/relationship protections, Ukrainian hard gate та structural/editorial gates залишаються hard requirements.
- Cache marker: `telegram-post-v22`, тому pending/retry RC36 drafts перегенеровуються за новим редакційним контрактом.

## Дані та portable-режим

SQLite-схема не змінена. Для оновлення розпакуйте RC37 у нову папку та перенесіть туди **всю папку `Data`** з RC36. Не накладайте runtime-файли поверх старої збірки.
