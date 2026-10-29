# Autopilot 2.2.54: editorial tone and Ukrainian micro-copyedit

Built from three **actual published** operator v2.2.53 Telegram post screenshots (29 October 2026):
- CTRL+UA, 16:09, Madagascar fruit bats: informative science and proper research limitation, but awkward Ukrainian **«не доказує причинність»** and risk of overstatement **«в промислових обсягах»**.
- ПРОДАНО!, 16:23, Japanese **dobedo studio ehho!²** folding pavilion: accurate mechanism and materials but weak editorial lead and overly technical second paragraph.
- ЗАПОРІЖЖЯ | ГРОМАДИ, 16:24, farewell to **Volodymyr Sorokolat**, a 41-year-old National Guard sapper: adequate factual reporting, but the impersonal **«Чоловік служив»** is tonally weak for a confirmed soldier's memorial.

Changes:
1. New **source-based tone contracts** in `v2/editorial_tone_254.py`. Only an explicit farewell/funeral **plus** military-service identity **plus** death gets the sober respectful memorial tone. Ordinary breaking fatality alerts and civilian notices do NOT inherit it. Source-bounded design object **plus** demonstrable physical folding/transformation gets a stronger mechanism-first lead with material detail second. Science guidance keeps correlation/causation separate and avoids amplifying unsupported commercial/intensity claims. Generic news remains fact-first.
2. Both already existing writer and final-editor prompts include **the same** tone guidance. Selection is role- and source-based, **never** numeric channel ID or name. No extra model call, no new delay, no category-specific hard-veto, no AI-cost increase or disabled outlet.
3. Narrow **safe language replacement** in `ukrainian_quality.py`: exact Ukrainian `не доказує причинність` → `не доводить причинно-наслідкового зв’язку`. Other uses of `не доказує` are unchanged. Already-existing deterministic safe-fix route is reused.
4. Focused positive/negative tests from these three posts; ordinary fatalities, civilian mourning, untargeted creative products and unverified «у промислових обсягах» are protected from forced rewriting.

Not modified: registered 36/18/57 sources, cooldowns, 45/30/5m intervals, OpenRouter $3/day and $20/month caps, media/provenance, Data/SQLite, emergency alerts, posting ledger, 1 protected historical UNKNOWN, AI routing, previous v2.2.53 teaser hydration. QA / Fact Guard is unchanged and remains authoritative.

Release gates: PR CI Ubuntu + Windows 3.11/3.12/3.13, native Windows Portable + Defender, official tag/ZIP and operator LIVE. Correct real editorial impact still needs new operator 2.2.54 posts (not simply green CI).
