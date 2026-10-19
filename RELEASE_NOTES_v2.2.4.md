# Autopilot 2.2.4 — Monitoring Event Types Operator Test

**Status:** Windows Portable TEST release, includes 2.2.3. Editorial LIVE acceptance is pending.

The LIVE review of 2.2.3 on 19.10 accepted ПРОДАНО! and CTRL+UA. ЗАПОРІЖЖЯ | ГРОМАДИ still published:
- "Загроза КАБ", "реактивний мопед" and "Орки знову закидають КАБами Оріхів";
- a lost-bag notice;
- three posts about the same «ВідНОВА:UA» programme.

These defects were not caused by 2.2.3: the same kinds of posts appeared on 17–18.10. Channel-specific behaviour is in channel settings; the mechanisms are universal.

## Fixes
- **Typed monitoring selector.** The AI selector now names the type of each source post: alert/threat, attack in progress, attack summary, private notice, missing person, initiative, local news, repost, ritual or other. The code then decides from the channel setting **"Заблоковані типи подій (моніторинг)"**. The default for monitoring channels is `alert_threat, attack_in_progress, private_ad, missing_person`. An "attack summary" counts only with a concrete result: casualties, damaged objects or official results. Otherwise it is treated as an attack in progress.
- **No ready-made answer in the prompt.** The old answer schema showed `"included":true,"excluded":false,"reason":"коротко"`, and weak models copied it: logs had the reason "коротко" and fit 100 for every post. The schema now holds no values. A copied placeholder, a missing type or a non-boolean field counts as an invalid answer, and the gateway tries another model.
- **Live-now gate vocabulary.** Added КАБ (whole word only, so "кабінет" and "кабель" are not affected), авіабомби, керовані, "реактивний мопед", РСЗВ, балістика, launch phrases, "будьте в укриттях", and attack verbs ("закидають", "гатять", "прилетіло" and similar). Attacks without a settled result are rejected before the AI step.
- **No padding of short notices.** For sources of up to 220 characters, the text may be at most 1.5× the source length (+20). Before, the minimum was 80 characters and the maximum was "+100". This forced models to invent details such as "Обстріл відбувся вранці…" or "будьте в укриттях" from a 30-character source.
- **One post per named initiative.** A quoted name next to an initiative word (програма, конкурс, акція, набір, реєстрація, …) is published once per channel window. The window is the setting **"Дедуп програм/кампаній, днів"**: 7 for monitoring channels, 0 (off) for editorial channels. A repeat with the community's own address or phone number is still published as a local event. Brands in quotes such as «Укрзалізниця» or «Дія» are not initiatives.

## Not changed
- **Time-based stitching of consecutive Telegram messages was not added.** In one week, 612 pairs of messages from the same source came within 3 minutes of each other, and nearly all were separate news. The split «ВідНОВА:UA» post is caught by the initiative rule.
- **Enemy claims** (e.g. the INFORM.ZP "Герасимов заявив…" post) are not changed, by operator decision.

## Validation
- New `tests/test_224_monitoring_event_types.py` (28 cases). The selector tests were updated to the new response schema. Full suite green locally.
- **Replay on the operator's real data** (copy of the 19.10 database, deterministic gates):
  - Of today's 29 ГРОМАДИ posts, 6 are blocked: "Загроза КАБ", "реактивний мопед", "Оріхів" and three «ВідНОВА:UA» repeats (the programme was already published on 13.10). Nothing else is blocked.
  - Over 269 posts in 7 days, the live-now gate adds 9 blocks. All are attacks without a settled result, e.g. "РСЗВ вдарило по Юрївці" and "ще відео наслідків прильоту".
  - The initiative rule adds no other blocks.
- **Migration on the copy:** only the monitoring channel gets the new defaults. CTRL+UA and ПРОДАНО! are unchanged.
- **Limitations:**
  - The lost-bag post (`private_ad`) and other type decisions need a live model. They are verified with unit tests, not offline replay.
  - Claim tracing stays diagnostic. A lexical trace showed many false "unresolved" claims on normal posts, so it is not used as a blocker.

## Installation
Stop Autopilot. Back up the complete `Data` folder. Unpack 2.2.4 into a new empty folder, move `Data` into it, and keep the previous folder for rollback. Never upload `Data/secrets.*`.

## Acceptance
In ГРОМАДИ there should be:
- no alerts, threats, launches or "в укриттях";
- attacks only with concrete results;
- no lost/found or search notices;
- one post per programme or contest per week;
- no added details beyond the source.

Normal community news should keep flowing. In Settings → channel → policy, check the two new fields.
