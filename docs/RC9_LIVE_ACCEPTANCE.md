# RC9 live acceptance checklist

RC9 is not stable until this checklist is completed on the real Windows workstation with a **copy** of the existing RC8 `Data`.

## Preparation

1. Close every Autopilot instance.
2. Keep the working RC8 folder untouched as rollback.
3. Extract RC9 to a new directory.
4. Copy the **entire** RC8 `Data` directory to RC9. Do not copy only `telegram_autopilot.sqlite3`; tokens and encryption material are separate files in the same directory.
5. Do not delete the RC8 copy after the first launch.

## Gate A: Data preservation

- Application starts without resetting channels, sources or history.
- Existing Telegram channel targets are still present.
- Existing source baselines remain initialized.
- Existing encrypted tokens remain readable.
- SQLite history counts do not unexpectedly collapse.

## Gate B: AI Router

- `AI та токени → Тест AI Router` completes and reports provider status without freezing the GUI.
- When cloud quota/errors occur, the task fails over instead of repeatedly waiting on the same provider.
- If local fallback is enabled, `Перевірити локальний AI` detects an already installed Ollama and an existing generation model.
- Ollama/model download is not triggered.
- A real approved article produces a full Ukrainian rewrite, not a short paraphrase or free-form commentary.

## Gate C: Ukrainian QA

Inspect several rewrites that contain technical/security terminology.

- Natural Ukrainian syntax, not literal English/Russian calques.
- `darknet/dark web` is rendered as `даркнет` / `даркнет-майданчик` when appropriate.
- `CRT/cathode-ray tube` is `електронно-променева трубка (ЕПТ)`.
- Names, numbers, attribution and uncertainty match the source facts.

## Gate D: Media selection

Use a small corpus that includes pages with ads, logos, generic `og:image`, real article figures and screenshots.

- Advertisement / sponsored / promo / Cocoon AI-summary images are not selected.
- Logos/avatars do not win over a relevant article-body image.
- A relevant body photo/screenshot/diagram is preferred when available.
- If there is no trustworthy editorial image, the Telegram post is allowed to have no image.
- Caption does not claim facts that are absent from source caption/alt metadata.
- A caption with an invented number or “the image proves/confirms...” is removed.

## Gate E: Controlled publication

Run at least one controlled new article through the full path:

source → decision → Ukrainian rewrite → media validation → Telegraph → Telegram.

Confirm:
- Telegraph article is complete and media order is sensible;
- Telegram teaser is readable and links to the Telegraph page;
- hero image is relevant or absent;
- retry does not create a duplicate Telegram message after a definite success;
- publication history records message ID, Telegraph URL and media count.

## Acceptance rule

Promote RC9 to `main` only after Gates A–E are PASS. Any reproducible data loss, broken token compatibility, GUI freeze, bad Ukrainian rewrite or clearly irrelevant advertising media is a release blocker.
