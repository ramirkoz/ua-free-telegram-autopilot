"""2.3.6: operator-calibrated editorial reset, preserving exact rollback text.

Calibration: 100 CTRL+UA + 100 PRODANO manually annotated by the operator on
2026-11-03; canonical reasoning in ProductVault. Selection remains source-bound,
while independent Fact/Media/Dedupe/Telegram gates remain hard.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from .domain import ChannelMode, DedupeProfile, EditorialRuntimeProfile
from .loghub import event
from .storage import now_iso

MARKER = "[EDITOR_HUMAN_236]"
MIGRATION_KEY = "human_editorial_236_applied"
BACKUP_KEY = "human_editorial_236_original_policies"
ROLLBACK_KEY = "human_editorial_236_operator_rollback"

SCIENCE = (
    "Наука й технології: цікаві, нові та перевірені факти без вимоги гучної сенсації.",
    "Україномовні допитливі читачі, не обов'язково професійні науковці чи інженери.",
    MARKER + " CTRL+UA — популярна наука й технології: космос, відкриття, дослідження, ШІ, "
    "робототехніка, кібербезпека, здоров'я і біологія, енергетика, клімат, винаходи, "
    "цікаві цифрові рішення та технологічні продукти. Самостійний достовірний результат "
    "або цікава нова концепція можуть бути новиною без доведеного світового прориву "
    "чи негайної масової користі. Оцінюй предметний факт, а не бренд чи престиж джерела.",
    MARKER + " Відхиляй рекламні купони, порожні анонси, рутину маркетингу, "
    "суто технічний changelog без змістовного результату, загальну політику без "
    "технологічного ядра, дублі та неперевірені заяви. Не вимагай одночасно "
    "революційності, масової користі, комерційного ефекту і вірусності.",
    MARKER + " Цікава інформація важливіша за абстрактний рейтинг. Редактор обрав: "
    "нові дані телескопа Вебба, план місячної програми, виявлення дронів через "
    "мобільні мережі, знешкодження Android-ботнету, робототехніку. "
    "Відкинув: купони, звичайну політичну риторику, порожній PR. "
    "Це ПРИКЛАДИ критеріїв, а не дозволи публікувати невірні факти. "
    "Відсутність підтверджених фактів є reject незалежно від цікавої теми.",
    MARKER + " Починай із підтвердженого результату чи нової ідеї простою українською. "
    "Поясни конкретику без вигаданих наслідків, термінів або сенсаційності.",
)
CREATIVE = (
    "Цікаві продукти, креатив, дизайн, реклама та оригінальні ідеї.",
    "Україномовні допитливі читачі, не обов'язково покупці чи маркетологи.",
    MARKER + " ПРОДАНО! — незвичайні товари, упаковка, предметний дизайн, "
    "оригінальні рекламні ідеї, креатив, винахідливі прототипи, цікаві функції, "
    "технологічні концепції й маркетингові кампанії. Справді цікава форма, "
    "функція чи дизайнерська ідея сама може бути повноцінною новиною. "
    "Не вимагай вірусності, брендової провокації, комерційного ROI чи глобального хайпу.",
    MARKER + " Відхиляй рутинні B2B/кадрові пресрелізи, банальні товари без "
    "незвичайного задуму, звичайні корпоративні звіти, рекламу без креативної "
    "ідеї, беззмістовні анонси, дублі та недоведені заяви. Короткий teaser вимагає "
    "перевірки точного повного першоджерела, але не доводить відсутності цінності.",
    MARKER + " Редактор обрав: Nike × LEGO, конус-дрон, Voxel, планшет MagBoard, "
    "тканини, які забарвлюють бактерії. Відкидав більшість рутинних агентських PR. "
    "Оціни саму оригінальну ідею та підтверджені деталі, а не потенційну "
    "вірусність чи вигадану поведінку аудиторії. Це НЕ whitelist брендів.",
    MARKER + " Розкажи, який предмет/проєкт створено, що саме незвичайне і "
    "як це підтверджено джерелом. Не домислюй продажів, популярності чи ефектів.",
)
CHANNEL_PROFILE = {
    "science": (
        "CTRL+UA — наука, космос, ШІ, робототехніка, кібербезпека та "
        "технології для допитливих читачів. Цікава предметна новина "
        "не зобов'язана бути революційною чи масовою сенсацією. "
        "Достовірність першоджерела, дедуплікація, факти й Telegram-безпека "
        "залишаються безумовними."
    ),
    "creative": (
        "ПРОДАНО! — незвичайні продукти, дизайн, цікаві речі, оригінальні "
        "рекламні й креативні ідеї. Справді нова форма, функція або концепція "
        "не зобов'язана доводити вірусність чи маркетингову віддачу. "
        "Рутинний B2B PR без ідеї, неперевірені твердження та дублікати "
        "не публікуються."
    ),
}

FIELDS = (
    "purpose", "audience", "selection_rules", "rejection_rules",
    "selector_extra_prompt", "writer_extra_prompt",
)


def _role(channel: Any) -> str:
    if str(getattr(channel, "mode", "")) != str(ChannelMode.EDITORIAL):
        return ""
    profile = str(getattr(channel, "editorial_runtime_profile", ""))
    dedupe = str(getattr(channel, "dedupe_profile", ""))
    # Commercial role is explicitly configured by the runtime profile;
    # dedupe profile is independently operator-configurable and not an identity.
    if profile == str(EditorialRuntimeProfile.COMMERCIAL_EDITORIAL):
        return "creative"
    if (profile == str(EditorialRuntimeProfile.STANDARD)
            and dedupe == str(DedupeProfile.SCIENTIFIC_NEWS)
            and bool(getattr(channel, "dedupe_scientific_names", False))
            and bool(getattr(channel, "dedupe_compound_events", False))):
        return "science"
    return ""


def calibrated_editorial_role(channel: Any) -> str:
    role = _role(channel)
    if role and MARKER in str(getattr(getattr(channel, "policy", None), "selection_rules", "") or ""):
        return role
    return ""


def apply_editorial_calibration_236(store: Any) -> dict[str, Any]:
    """Transactional one-time role-scoped policy reset with exact old values.

    Call AFTER 2.3.5 source import, science RC103 and general audience migration,
    BEFORE worker start. A missing channel is not marked as migrated.
    """
    updated: list[tuple[int, str]] = []
    with store.transaction() as con:
        con.execute("BEGIN IMMEDIATE")
        previous_rollback = con.execute("SELECT value FROM meta WHERE key=?", (ROLLBACK_KEY,)).fetchone()
        if previous_rollback:
            con.commit()
            return {"status": "operator_rolled_back", "roles": [], "count": 0}
        marker = con.execute("SELECT value FROM meta WHERE key=?", (MIGRATION_KEY,)).fetchone()
        if marker and str(marker[0] or "") == "1":
            con.commit()
            return {"status": "already_applied", "roles": [], "count": 0}
        rows = con.execute(
            """SELECT c.id,c.channel_mode,c.editorial_runtime_profile,
                      c.dedupe_profile,c.dedupe_scientific_names,
                      c.dedupe_compound_events,c.editorial_profile,
                      p.purpose,p.audience,p.selection_rules,p.rejection_rules,
                      p.selector_extra_prompt,p.writer_extra_prompt
               FROM channels c JOIN channel_policies p ON p.channel_id=c.id
               WHERE c.channel_mode='editorial'"""
        ).fetchall()
        previous: dict[str, dict[str, str]] = {}
        for row in rows:
            channel = SimpleNamespace(
                mode=row["channel_mode"],
                editorial_runtime_profile=row["editorial_runtime_profile"],
                dedupe_profile=row["dedupe_profile"],
                dedupe_scientific_names=bool(row["dedupe_scientific_names"]),
                dedupe_compound_events=bool(row["dedupe_compound_events"]),
            )
            role = _role(channel)
            if not role:
                continue
            cid = int(row["id"])
            previous[str(cid)] = {key: str(row[key] or "") for key in FIELDS}
            previous[str(cid)]["editorial_profile"] = str(row["editorial_profile"] or "")
            policy = SCIENCE if role == "science" else CREATIVE
            con.execute(
                """UPDATE channel_policies SET
                   purpose=?,audience=?,selection_rules=?,rejection_rules=?,
                   selector_extra_prompt=?,writer_extra_prompt=?,updated_at=?
                   WHERE channel_id=?""",
                (*policy, now_iso(), cid),
            )
            con.execute(
                "UPDATE channels SET editorial_profile=?,updated_at=? WHERE id=?",
                (CHANNEL_PROFILE[role], now_iso(), cid),
            )
            updated.append((cid, role))
        if updated:
            con.execute(
                "INSERT INTO meta(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (BACKUP_KEY, json.dumps(previous, ensure_ascii=False)),
            )
            con.execute("INSERT INTO meta(key,value) VALUES(?,?)",
                        (MIGRATION_KEY, "1"))
        con.commit()
    event("editorial", "2.3.6 human-labelled policy applied",
          count=len(updated), roles=",".join(role for _, role in updated))
    return {"status": "applied" if updated else "no_target_channels",
            "count": len(updated), "roles": [role for _, role in updated]}


def rollback_editorial_calibration_236(store: Any) -> int:
    """Operator-invoked rollback helper, never called automatically."""
    with store.transaction() as con:
        con.execute("BEGIN IMMEDIATE")
        stored = con.execute("SELECT value FROM meta WHERE key=?", (BACKUP_KEY,)).fetchone()
        if not stored:
            con.commit()
            return 0
        previous = json.loads(str(stored[0]))
        changed = 0
        for id_str, old in previous.items():
            cid = int(id_str)
            if not isinstance(old, dict) or not all(k in old for k in FIELDS):
                continue
            con.execute(
                """UPDATE channel_policies SET
                   purpose=?,audience=?,selection_rules=?,rejection_rules=?,
                   selector_extra_prompt=?,writer_extra_prompt=?,updated_at=?
                   WHERE channel_id=?""",
                (*(str(old[key]) for key in FIELDS), now_iso(), cid),
            )
            changed += con.execute("SELECT changes()").fetchone()[0]
            if "editorial_profile" in old:
                con.execute(
                    "UPDATE channels SET editorial_profile=?,updated_at=? WHERE id=?",
                    (str(old["editorial_profile"]), now_iso(), cid),
                )
        con.execute("DELETE FROM meta WHERE key=?", (MIGRATION_KEY,))
        con.execute("INSERT INTO meta(key,value) VALUES(?,?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (ROLLBACK_KEY, "1"))
        con.commit()
    return changed
