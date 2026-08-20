# UA FREE Telegram Autopilot v0.1.0-rc25

RC25 is a production-language reliability hotfix over RC24.

- LanguageTool is mandatory for automatic publication. If it is still installing/starting, the current article is delayed and the cycle pauses instead of publishing unchecked Ukrainian or poisoning the whole queue.
- LanguageTool status is visible in the AI tab and startup/install events are written into the durable audit trail.
- AI Router test now adds a production-sized Ukrainian rewrite probe, not only tiny endpoint pings.
- Local fallback gets a larger guaranteed time reserve and a 75-second production timeout.
- Final deterministic Ukrainian gate fixes/blocks gross live RC24 errors such as «гучний гудіння», «над водой», «тепловий мап», «прямий у басейн», «терміни релізу немає».
- Every final LanguageTool/deterministic edit is revalidated against numbers, years and Fact Guard.
- Pending/retry marker: telegram-post-v15.

Collector, media/video pipeline, Telegram publisher, event dedupe and database schema are unchanged.
