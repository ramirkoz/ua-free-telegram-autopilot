# UA FREE Telegram Autopilot v0.1.0-rc82

RC82 Stable Night повертає перевірену редакційну поведінку RC79/RC80 та прибирає з активного runtime зламаний RC81 Codex model pin.

- збережені ChannelPolicy та налаштування кожного каналу залишаються авторитетними;
- monitoring використовує тільки явно збережені inclusion/exclusion rules і більше не fail-open при аварії AI;
- RC79 Telegram stitching, donor media, media_policy, actionable facts і компактні source links збережені;
- RC80 strict same-event dedupe збережений;
- Codex більше не має hardcoded GPT-моделі: використовується список моделей, який повертає сам ChatGPT/Codex account, default-модель пробується першою;
- Codex runtime 0.147.0 встановлюється side-by-side без перезапису завантажених DLL/PYD;
- SELECTOR_UNAVAILABLE є технічним WAITING_AI/retry, а не редакційним reject;
- зовнішній AI outage не переводить матеріал у terminal error після фіксованої кількості спроб;
- повернення здорового AI автоматично будить невелику частину WAITING_AI backlog; свіжі NEW матеріали все одно мають пріоритет;
- Telegram publish заборонений, якщо у матеріалу/кластера немає валідного canonical source URL. Посилання всередині тексту джерелом не вважається;
- RC81 startup recovery і hardcoded `gpt-5.4` не запускаються.
