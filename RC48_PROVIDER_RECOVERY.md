# RC48 provider recovery

Goal: keep direct Gemini, Groq and NVIDIA routes operational under short provider-side throttling/capacity events.

Implementation:
- shared per-host pacing across channel workers;
- bounded retry for HTTP 429/5xx and transport timeouts;
- Retry-After and Google RetryInfo delay parsing;
- Gemini stable Flash-Lite fallback;
- Groq GPT-OSS 20B fallback;
- NVIDIA 503 retry before route failover;
- explicit hard quota detection only for clear account/daily exhaustion signals.
