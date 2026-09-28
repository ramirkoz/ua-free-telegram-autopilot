from __future__ import annotations

import json

from .domain import ChannelMode, EditorialRuntimeProfile
from .monitoring_live_now import install_monitoring_live_now_gate
from .storage import now_iso

_POLL_MARKER = "rc90_poll_interval_15m_repair_v1"
_LIVE_NOW_MARKER = "rc96_monitoring_live_now_policy_v1"
_PRODANO_PROFILE_MARKER = "rc98_commercial_manual_positive_profile_v1"
_LIVE_NOW_BLOCK = (
    "[LIVE_NOW_RC96]\n"
    "Не публікувати оперативні події, цінність яких існує лише прямо зараз або кілька хвилин: "
    "повітряна тривога/відбій/загроза; поточний рух, проліт, курс або напрямок БпЛА, ракет, "
    "авіації чи інших повітряних цілей (у т.ч. евфемізми на кшталт ‘мопед’); ‘зараз палає/горить’, "
    "‘щойно/тільки що пролетіло/побачили/зафіксували’. 15-хвилинний цикл робить такі повідомлення "
    "застарілими. Дозволені стійкі факти й наслідки після події: було атаковано, пошкоджено, відкрили, "
    "побудували, знайшли, а також майбутні заплановані зміни на кшталт ‘завтра змінять маршрут’."
)

_PRODANO_SELECTION_BLOCK = """[MANUAL_POSITIVE_SET_RC98]
Це не вузький trade-маркетинг канал. Відбирай історії, які хочеться показати іншій людині навіть поза професійним маркетинговим середовищем.
Сильні сигнали: дивність/новизна; візуальний або відео-гачок; віральність; культурний момент; попкультура; незвичний продукт або дизайн; брендова провокація чи stunt; нестандартне застосування AI/технологій; людська поведінка або дослідження з неочікуваним і легко переказуваним результатом.
Бренд або рекламна кампанія не обов'язкові. Матеріал може бути про технологію, кіно/серіал/гру, дизайн, інтернет-феномен, поведінку людей або дивний реальний об'єкт, якщо є конкретний сильний гачок.
Відео/сильне медіа є позитивним сигналом, особливо коли саме демонстрація робить історію зрозумілою або віральною, але саме по собі медіа не рятує нудний матеріал."""

_PRODANO_REJECTION_BLOCK = """[TRADE_NOISE_RC98]
Відхиляй сухі галузеві новини без сильного людського/візуального гачка: звичайні призначення керівників, HR/career, квартальні корпоративні апдейти, типові retail/martech/search/PR новини, звичайні партнерства, стандартні запуски продукту, B2B-аналітику й професійний жаргон заради жаргону.
Не публікуй матеріал лише тому, що в ньому є бренд, реклама або слово campaign. Має бути конкретна ідея, конфлікт, дивність, культурний сигнал, корисний механізм або візуально сильне виконання."""

_PRODANO_SELECTOR_PROMPT = """Орієнтир редактора: ручні пости каналу тяжіють до IKEA-манула, Pokémon-кедів Adidas, AI-пошуку загублених котів, спірального Lexus від MSCHF, віральної тіні Aston Martin, Apple backstage, мегаяхти-носія, робота-гусака, резюме на торті, книжкових рейвів та подібних історій. Це приклади типу інтересу, а не whitelist тем чи брендів.
Для fit спочатку запитай: «чи це легко показати/переказати другові і чи є тут конкретне незвичне ядро?». Високо оцінюй visual/video payoff, weirdness, novelty, virality, culture hook і human interest. Сухий trade relevance без такого ядра оцінюй низько."""

_PRODANO_POSITIVE_EXAMPLES = """Ручна еталонна вибірка редактора: IKEA випускає плюшевого манула з сердитою мордою; Adidas робить Pokémon-кеди з вухами Пікачу; AI-проєкт шукає загублених котів через камери/GPS; MSCHF скручує Lexus у спіральну скульптуру; тінь дверей Aston Martin стає віральним фалічним жартом; Apple показує backstage stop-motion реклами; мегаяхта перевозить іншу яхту, літак і десятки машин; робот-гусак як домашній помічник; кандидатка надсилає резюме на торті; у клубах проводять книжкові рейви; Cup Noodles робить криваво-червону Halloween-локшину; Snapchat запускає AR-гру Harry Potter."""

# Existing sources are configuration, not editorial core.  RC98 only changes the
# persisted source mix of channels that explicitly use the commercial-editorial
# profile. Unknown/custom sources are left untouched.
_PRODANO_SOURCE_DISABLE = {
    "modern retail",
    "retail dive",
    "packaging europe",
    "prweek",
    "search engine land",
    "martech",
    "warc",
    "marketing week",
    "marketing brew",
    "tiktok for business blog",
}
_PRODANO_SOURCE_PRIORITY = {
    "ads of the world": 15,
    "campaign brief": 15,
    "shots": 20,
    "creative boom": 25,
    "it's nice that": 25,
    "it’s nice that": 25,
    "social samosa": 35,
    "brand new / underconsideration": 40,
    "trend hunter": 55,
    "ad age": 140,
    "fast company": 150,
    "springwise": 160,
}


def _repair_monitoring_live_now_policy(con) -> int:
    row = con.execute("SELECT value FROM meta WHERE key=?", (_LIVE_NOW_MARKER,)).fetchone()
    if row and str(row[0] or "") == "1":
        return 0
    rows = con.execute(
        """SELECT c.id,p.rejection_rules
             FROM channels c JOIN channel_policies p ON p.channel_id=c.id
            WHERE c.channel_mode=?""",
        (str(ChannelMode.MONITORING),),
    ).fetchall()
    changed = 0
    stamp = now_iso()
    for item in rows:
        base = str(item["rejection_rules"] or "").strip()
        if "[LIVE_NOW_RC96]" in base:
            continue
        merged = (base + "\n\n" + _LIVE_NOW_BLOCK).strip() if base else _LIVE_NOW_BLOCK
        con.execute(
            "UPDATE channel_policies SET rejection_rules=?,updated_at=? WHERE channel_id=?",
            (merged, stamp, int(item["id"])),
        )
        changed += 1
    con.execute(
        "INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (_LIVE_NOW_MARKER, "1"),
    )
    return changed


def _append_once(base: str, marker: str, block: str) -> str:
    value = str(base or "").strip()
    if marker in value:
        return value
    return (value + "\n\n" + block).strip() if value else block


def _repair_commercial_manual_profile(con) -> dict[str, int]:
    row = con.execute("SELECT value FROM meta WHERE key=?", (_PRODANO_PROFILE_MARKER,)).fetchone()
    if row and str(row[0] or "") == "1":
        return {"channels": 0, "sources_disabled": 0, "sources_prioritized": 0}

    channels = con.execute(
        """SELECT c.id,c.editorial_thresholds_json,
                  p.selection_rules,p.rejection_rules,p.selector_extra_prompt,p.positive_examples
             FROM channels c JOIN channel_policies p ON p.channel_id=c.id
            WHERE c.editorial_runtime_profile=?""",
        (str(EditorialRuntimeProfile.COMMERCIAL_EDITORIAL),),
    ).fetchall()
    stamp = now_iso()
    disabled = prioritized = 0
    for item in channels:
        channel_id = int(item["id"])
        try:
            thresholds = json.loads(str(item["editorial_thresholds_json"] or "{}"))
        except Exception:
            thresholds = {}
        if not isinstance(thresholds, dict):
            thresholds = {}
        thresholds.update({
            "broad_interest_fit": 58,
            "broad_interest_score": 54,
            "broad_general_interest": 54,
            "broad_retellability": 54,
            "broad_culture_or_surprise": 48,
            "creative_case_fit": 60,
            "creative_case_score": 46,
            "creative_execution": 62,
            "creative_anchor": 48,
        })
        con.execute(
            """UPDATE channels
               SET media_first_allowed=1,media_min_text_chars=120,
                   editorial_thresholds_json=?,updated_at=?
               WHERE id=?""",
            (json.dumps(thresholds, ensure_ascii=False, separators=(",", ":")), stamp, channel_id),
        )
        con.execute(
            """UPDATE channel_policies
               SET purpose=?,audience=?,selection_rules=?,rejection_rules=?,
                   selector_extra_prompt=?,positive_examples=?,updated_at=?
               WHERE channel_id=?""",
            (
                "Живий візуальний дайджест дивних, нових і легко переказуваних історій про бренди, технології, дизайн, попкультуру, інтернет і поведінку людей.",
                "Широка допитлива аудиторія, не лише маркетологи. Читач має отримати конкретний привід здивуватися, показати матеріал іншому або переказати його.",
                _append_once(str(item["selection_rules"] or ""), "[MANUAL_POSITIVE_SET_RC98]", _PRODANO_SELECTION_BLOCK),
                _append_once(str(item["rejection_rules"] or ""), "[TRADE_NOISE_RC98]", _PRODANO_REJECTION_BLOCK),
                _append_once(str(item["selector_extra_prompt"] or ""), "Орієнтир редактора:", _PRODANO_SELECTOR_PROMPT),
                _append_once(str(item["positive_examples"] or ""), "Ручна еталонна вибірка редактора:", _PRODANO_POSITIVE_EXAMPLES),
                stamp,
                channel_id,
            ),
        )
        sources = con.execute(
            "SELECT id,name,priority,enabled FROM sources WHERE channel_id=?",
            (channel_id,),
        ).fetchall()
        for source in sources:
            name = str(source["name"] or "").strip().casefold()
            if name in _PRODANO_SOURCE_DISABLE and int(source["enabled"] or 0):
                con.execute("UPDATE sources SET enabled=0 WHERE id=?", (int(source["id"]),))
                disabled += 1
            priority = _PRODANO_SOURCE_PRIORITY.get(name)
            if priority is not None and int(source["priority"] or 100) != int(priority):
                con.execute("UPDATE sources SET priority=? WHERE id=?", (int(priority), int(source["id"])))
                prioritized += 1

    con.execute(
        "INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (_PRODANO_PROFILE_MARKER, "1"),
    )
    return {"channels": len(channels), "sources_disabled": disabled, "sources_prioritized": prioritized}


def repair_polling_baseline(store) -> dict[str, object]:
    """Apply durable post-import repairs while keeping the startup return contract."""
    install_monitoring_live_now_gate()
    with store.connect() as con:
        _repair_monitoring_live_now_policy(con)
        commercial = _repair_commercial_manual_profile(con)
        row = con.execute("SELECT value FROM meta WHERE key=?", (_POLL_MARKER,)).fetchone()
        if row and str(row[0] or "") == "1":
            return {
                "repaired": False,
                "reason": "already_applied",
                "channels_changed": 0,
                "commercial_profile": commercial,
            }

        total = int(con.execute("SELECT COUNT(*) FROM channels").fetchone()[0] or 0)
        if total <= 0:
            return {
                "repaired": False,
                "reason": "no_channels",
                "channels_changed": 0,
                "commercial_profile": commercial,
            }

        changed = int(con.execute("SELECT COUNT(*) FROM channels WHERE poll_interval_minutes<15").fetchone()[0] or 0)
        if changed:
            con.execute(
                "UPDATE channels SET poll_interval_minutes=15,updated_at=? WHERE poll_interval_minutes<15",
                (now_iso(),),
            )
        con.execute(
            "INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (_POLL_MARKER, "1"),
        )
        return {
            "repaired": bool(changed),
            "reason": "baseline_applied",
            "channels_changed": changed,
            "channels_total": total,
            "commercial_profile": commercial,
        }
