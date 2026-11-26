# Autopilot 2.3.61 — conservative provider recovery

- Based on the exact installed 2.3.60 candidate. Production routing contract is unchanged: OpenRouter serves all content purposes while usable; existing emergency failover remains unchanged. No free writer/selector is promoted automatically.
- Groq and Cloudflare manual health checks test every configured model independently, without hidden model fallback. Probe budget 1024 tokens; transport timeout 35 seconds per attempt; require the exact requested model and final OK. Reasoning-only output is not a success. Network/DNS, quota, model and authentication failures remain visible.
- Groq GPT-OSS uses supported low reasoning effort directly; Qwen3.8 retains supported none. No changes to editorial prompts, selectors, source/media QA, deduplication, schedules, provider ordering, global/per-article paid admission, delivery journal or operator settings.
- Optional manual comparison module captures the current production writer prompt and validator, then stops the production writer before any paid call or publication. A reviewed direct model can generate one candidate per selected stored published article; current local writer and prepublish QA checks run. Exact model identity is required. No runtime import, no auto-promotion, no OpenRouter calls, no Telegram calls, no DB/secrets writes. The report contains public source and published baseline plus candidate; store it locally and review before sharing. Current policy and reconstructed angle may differ from those at original publication. A QA pass alone does not prove equivalent final quality. Direct provider accounts may charge depending on quota/billing; explicitly confirm before running.
- This is a locally assembled Windows Portable candidate. Native Windows and authenticated direct-provider API acceptance remain to be verified.

## Оператору

1. Зробіть резервну копію Data звичайним способом; не видаляйте поточну 2.3.60. Встановіть повний Portable в окрему папку та перенесіть дані штатним механізмом.
2. Запустіть програму, натисніть штатну кнопку перевірки AI, перевірте окремо результати Groq і Cloudflare в телеметрії. DNS-помилка потребує перевірки мережі Windows; код не змінює системні DNS або проксі.
3. Виробничий режим залишено OpenRouter. Ручний експеримент не є необхідним для роботи програми. Для нього зупиніть програму, відкрийте PowerShell у каталозі Portable, оберіть ідентифікатори вже опублікованих матеріалів із публічних джерел, перевірте тариф прямого API, виконайте (приклад):

```powershell
.\python.exe -m telegram_autopilot.v2.provider_trial_2361 --provider gemini --model gemini-3.5-flash --article 115010 115146 115161 --output .\provider_trial_gemini.json --confirm-direct-api
```

Не більш ніж 9 статей за запуск, без автоматичної публікації. Якщо Data розміщено в іншому каталозі, вкажіть `--data` з фактичним шляхом. Для інших моделей дозволено: `nvidia/nemotron-3-ultra-550b-a55b` (nvidia), `openai/gpt-oss-120b` або `qwen/qwen3.8-27b` (groq), `@cf/google/gemma-4-26b-a4b-it` або `@cf/zai-org/glm-4.7-flash` (cloudflare). Усе, що не пройшло QA, залишається лише діагностичним результатом. Не змінюйте режим маршрутизації за результатом одного тесту.
