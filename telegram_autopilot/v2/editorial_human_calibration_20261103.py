"""Operator-calibrated editorial policy, based on 200 manually labelled stories.

The policy intentionally replaces accumulated subjective prompt layers rather
than adding another veto. It does not change article history, source records,
delivery receipts, publication cadence, or monitoring-channel preferences.
"""
from __future__ import annotations

import json
from typing import Any

from .domain import ChannelMode, DedupeProfile, EditorialRuntimeProfile
from .loghub import event
from .storage import now_iso

MARKER = "[HUMAN_EDITOR_20261103]"
MIGRATION_KEY = "human_editorial_20261103_applied"
BACKUP_KEY = "human_editorial_20261103_previous_policies"

SCIENCE_SELECTION = (
    MARKER + " CTRL+UA: популярна наука й технології для допитливої аудиторії. "
    "Обирай конкретне нове знання, відкриття, дослідження, космічну подію, "
    "технологію, кібербезпеку, корисний винахід, ШІ, роботів, біологію, "
    "медицину, клімат і техніку з цікавою предметною суттю. "
    "Новизна може бути в самому результаті, а не тільки у доведеному "
    "світовому прориві. Технологічний продукт не є автоматично нецікавим. "
    "Поясни, що нового і чому читач може захотіти це знати, тільки за SOURCE."
)
SCIENCE_REJECTION = (
    MARKER + " Відхиляй рекламу/промокоди, порожні анонси, політику без "
    "науково-технологічного ядра, звичайний патч/бенчмарк/частоту чи деталь "
    "для розробників без змістовної новини, недоведені заяви та повтори. "
    "НЕ вимагай водночас комерціалізації, масового ефекту та революційності."
)
SCIENCE_SELECTOR = (
    MARKER + " Перевага предметної цікавої новини. Позитивні редакторські "
    "приклади: космічна програма, відкриття Webb, Android-ботнет, використання "
    "мобільних мереж для виявлення дронів. Негативні: рекламні купони, "
    "звичайні технічні характеристики без цікавої історії. Це приклади "
    "КРИТЕРІЇВ, не список брендів чи тем для безумовного схвалення."
)
SCIENCE_WRITER = (
    MARKER + " Перше речення: перевірений зміст новини простою українською. "
    "Далі поясни відкриття/продукт і фактичний контекст; без вигаданих "
    "наслідків, жаргону, штучного сенсаційного тону та некоректних термінів."
)

CREATIVE_SELECTION = (
    MARKER + " ПРОДАНО!: незвичайні товари, предметний/промисловий дизайн, "
    "пакування, креативні рекламні ідеї, маркетинг, мистецькі й технологічні "
    "концепції, цікаві прототипи та нетривіальні способи використання речей. "
    "Нова оригінальна функція, форма чи історія сама по собі має редакційну "
    "цінність. НЕ вимагай вірусності, культурної сенсації, комерційних "
    "показників або широкого хайпу, якщо SOURCE підтверджує саму ідею."
)
CREATIVE_REJECTION = (
    MARKER + " Відхиляй рутинні B2B PR/кадрові релізи, банальні товари "
    "без особливості, рекламні заклики без ідеї, непідтверджені заяви "
    "та повтори. Короткий анонс потребує точного першоджерела, але "
    "сам по собі не доводить, що ідея нецікава."
)
CREATIVE_SELECTOR = (
    MARKER + " Перевір самостійну креативну ідею, а не нав'язану "
    "маркетингову механіку. Позитивні приклади редактора: Nike × LEGO, "
    "дорожній конус-дрон, робот Voxel, MagBoard, тканини, пофарбовані "
    "бактеріями. Негативні: масові корпоративні пресрелізи без "
    "цікавого продукту/ідеї. Не вигадуй враження аудиторії."
)
CREATIVE_WRITER = (
    MARKER + " Почни з того, що саме зробили і в чому незвичайна "
    "оригінальна ідея. Поясни коротко фактичний механізм і деталі. "
    "Не додавай вірусності, популярності чи продажів без джерела."
)

POLICY_FIELDS = (
    "purpose", "audience",
    "selection_rules", "rejection_rules",
    "selector_extra_prompt", "writer_extra_prompt",
)


def _role(channel: Any) -> str:
    """Identity is configuration, not numeric channel id or channel name."""
    if str(getattr(channel, "mode", "")) != str(ChannelMode.EDITORIAL):
        return ""
    profile = str(getattr(channel, "editorial_runtime_profile", ""))
    dedupe = str(getattr(channel, "dedupe_profile", ""))
    if profile == str(EditorialRuntimeProfile.COMMERCIAL_EDITORIAL):
        return "creative"
    if (
        profile == str(EditorialRuntimeProfile.STANDARD)
        and dedupe == str(DedupeProfile.SCIENTIFIC_NEWS)
        and bool(getattr(channel, "dedupe_scientific_names", False))
        and bool(getattr(channel, "dedupe_compound_events", False))
    ):
        return "science"
    return ""


def human_calibrated_editorial(channel: Any) -> bool:
    return bool(
        _role(channel)
        and MARKER in str(getattr(getattr(channel, "policy", None), "selection_rules", "") or "")
    )


def apply_human_editorial_policy(store: Any) -> int:
    """Transactional one-time replacement with exact backup for rollback.

    Must run AFTER historical channel migrations and BEFORE collector/worker
    startup. Existing operator Data is not copied, erased or rebuilt.
    """
    with store.connect() as con:
        row = con.execute("SELECT value FROM meta WHERE key=?", (MIGRATION_KEY,)).fetchone()
        if row and str(row[0]) == "1":
            return 0
        channels = con.execute(
            """SELECT c.id,c.channel_mode,c.editorial_runtime_profile,
                      c.dedupe_profile,c.dedupe_scientific_names,c.dedupe_compound_events,
                      p.purpose,p.audience,p.selection_rules,p.rejection_rules,
                      p.selector_extra_prompt,p.writer_extra_prompt
               FROM channels c JOIN channel_policies p ON p.channel_id=c.id
               WHERE c.channel_mode='editorial'"""
        ).fetchall()
        changes: list[tuple[int, str]] = []
        prior: dict[str, dict[str, str]] = {}
        stamp = now_iso()
        for row in channels:
            from types import SimpleNamespace
            channel = SimpleNamespace(
                mode=ChannelMode.EDITORIAL,
                editorial_runtime_profile=row["editorial_runtime_profile"],
                dedupe_profile=row["dedupe_profile"],
                dedupe_scientific_names=bool(row["dedupe_scientific_names"]),
                dedupe_compound_events=bool(row["dedupe_compound_events"]),
            )
            role = _role(channel)
            if not role:
                continue
            cid = int(row["id"])
            prior[str(cid)] = {field: str(row[field] or "") for field in POLICY_FIELDS}
            new_policy = (
                ("Цікава наука й технології, зрозумілі українською.",
                 "Допитливі читачі, не обов'язково фахівці.",
                 SCIENCE_SELECTION, SCIENCE_REJECTION, SCIENCE_SELECTOR, SCIENCE_WRITER)
                if role == "science" else
                ("Оригінальні продукти, дизайн, креатив і незвичайні ідеї.",
                 "Допитливі читачі, не обов'язково маркетологи чи дизайнери.",
                 CREATIVE_SELECTION, CREATIVE_REJECTION, CREATIVE_SELECTOR, CREATIVE_WRITER)
            )
            con.execute(
                """UPDATE channel_policies
                   SET purpose=?,audience=?,selection_rules=?,rejection_rules=?,
                       selector_extra_prompt=?,writer_extra_prompt=?,updated_at=?
                   WHERE channel_id=?""",
                (*new_policy, stamp, cid),
            )
            changes.append((cid, role))
        if changes:
            con.execute(
                "INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (BACKUP_KEY, json.dumps(prior, ensure_ascii=False)),
            )
            con.execute(
                "INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (MIGRATION_KEY, "1"),
            )
    if changes:
        event("editorial", "operator-calibrated policy installed", channels=len(changes),
              roles=",".join(role for _, role in changes), marker=MARKER)
    return len(changes)
