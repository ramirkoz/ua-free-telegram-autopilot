# UA FREE Telegram Autopilot v2.0.0-rc48

## Provider recovery under rate limits and transient outages

RC48 focuses on making direct Gemini, Groq and NVIDIA routes actually recover and produce completions instead of being parked after one transient provider response.

- Adds conservative per-host request pacing so multiple channel workers cannot self-trigger provider RPM limits as easily.
- Retries short HTTP 429 and 5xx/503 failures with bounded backoff and respects `Retry-After` / Google-style retry delay hints.
- Treats a bare 429 as transient unless the provider response explicitly indicates hard daily/account quota exhaustion.
- Adds direct Gemini fallback from `gemini-3.5-flash` to stable Flash-Lite models when a model lane is temporarily limited.
- Adds direct Groq fallback to production `openai/gpt-oss-20b` when the requested Groq model is temporarily rate-limited or unavailable.
- Keeps NVIDIA on the official free NIM endpoint and retries temporary 503 capacity failures before falling through to the second reviewed NVIDIA model.
- Codex usage-limit handling remains unchanged: an explicit ChatGPT/Codex usage cap continues to be respected until its reset time.
- Cloudflare and local AI behavior remain unchanged.

Existing V2 `Data` remains compatible.
