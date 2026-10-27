"""CTRL+UA-type scientific/news profile: broad science and technology, not component hobby news.

Role-based, persisted, reversible via visible channel settings. This changes no
channel identity, source roster, publish cadence, safety or delivery metadata.
"""
from __future__ import annotations

import json
from typing import Any, Mapping

from .domain import ChannelMode, DedupeProfile, EditorialRuntimeProfile
from .loghub import event
from .storage import now_iso

MARKER = "[SCIENCE_GENERAL_AUDIENCE_V2]"
OLD_MARKER = "[SCIENTIFIC_NEWS_RC103]"
MIGRATION_KEY = "science_general_audience_v2_migrated"

WEIGHTS = [
    {"name": "Science / Space", "weight": 30},
    {"name": "Medicine / Biology", "weight": 17},
    {"name": "AI", "weight": 18},
    {"name": "Robotics", "weight": 12},
    {"name": "Energy / Climate", "weight": 10},
    {"name": "Defense / Ukraine tech", "weight": 5},
    {"name": "Cybersecurity", "weight": 5},
    {"name": "Hardware", "weight": 3},
]

SELECTION = (
    MARKER + "\n"
    "Наука й технології для широкої розумної аудиторії, не для розробників компонентів. "
    "Перевага: важливі відкриття, космос, медицина, біотехнології, AI з реальним результатом, "
    "робототехніка, транспорт, енергетика, довкілля, масштабні інновації та відкриття про природу. "
    "Редакційна цінність визначається ПІДТВЕРДЖЕНИМ наслідком, масштабом, здивуванням, "
    "новим знанням або зрозумілим людським застосуванням. "
    "Одна нова цифра, кращий компонент або локальний лабораторний трюк самі по собі НЕ новина."
)
REJECTION = (
    MARKER + "\n"
    "ВІДХИЛЯЙ матеріали лише для інженерів, геймерів і розробників: "
    "зміни напруги, частоти, контролерів, прошивок, транзисторів, плат, драйверів, "
    "характеристик чипів, benchmarks, DIY-проєкти та мінорні апдейти. "
    "Виняток тільки коли першоджерело доводить чіткий суспільний, науковий, "
    "медичний чи технологічний прорив/ефект. Не додумуй користь з потенційних можливостей. "
    "Не відхиляй справді важливе фундаментальне відкриття тільки тому, що воно не має продукту."
)
SELECTOR = (
    MARKER + " SCIENCE/TECH FOR ORDINARY CURIOUS READERS, NOT A HARDWARE/DEV BLOG. "
    "A component-level improvement or small benchmark/voltage/firmware update without "
    "verified broad consequence is reject (weak_audience_hook), regardless of novelty. "
    "Prefer discoveries, transformative technology, space, health, research, and "
    "meaningful outcomes. Judge human/public interest using the ORIGINAL SOURCE only; "
    "never imagine future benefits. If only an engineer would retell it, reject."
)
WRITER = (
    MARKER + " Першим реченням назви новину просто. Поясни, що саме доведено і чому це "
    "цікаво звичайній людині. Менше технічного жаргону, не перераховуй специфікації "
    "без практичного сенсу. Не вигадуй перспективи або результатів, відсутніх у джерелі."
)


def is_science_general_channel(channel: Any) -> bool:
    """Target role only; numeric ID, name and Telegram handle are not selectors."""
    return (
        str(getattr(channel, "mode", "")) == str(ChannelMode.EDITORIAL)
        and str(getattr(channel, "editorial_runtime_profile", "")) == str(EditorialRuntimeProfile.STANDARD)
        and str(getattr(channel, "dedupe_profile", "")) == str(DedupeProfile.SCIENTIFIC_NEWS)
        and bool(getattr(channel, "dedupe_scientific_names", False))
        and bool(getattr(channel, "dedupe_compound_events", False))
    )


def broad_science_value_rejection(value: Mapping[str, Any]) -> str:
    """Independent audience check after ordinary editorial value gate.

    A niche micro-improvement with no demonstrated consequence must not pass a
    high technical novelty/mechanism score. Significant *fundamental* discoveries
    can still pass through strong genuine curiosity and retellability.
    """
    def score(key: str) -> int:
        try:
            return max(0, min(100, int(float(value.get(key, 0) or 0))))
        except (TypeError, ValueError):
            return 0

    retell = score("retellability")
    payoff = score("reader_payoff")
    consequence = score("consequence_or_insight")
    stakes = score("concrete_stakes")
    novelty = score("novelty")
    if retell < 62 or payoff < 60:
        return "SCIENCE_AUDIENCE_REJECT: only narrow technical audience"
    if max(consequence, stakes) < 58 and not (novelty >= 85 and retell >= 76 and payoff >= 72):
        return "SCIENCE_AUDIENCE_REJECT: no verified broad significance or fundamental discovery"
    return ""


def _replace_old_block(raw: str, block: str) -> str:
    pieces = [part.strip() for part in str(raw or "").split("\n\n")]
    pieces = [
        part for part in pieces
        if part and not part.startswith(OLD_MARKER) and not part.startswith(MARKER)
    ]
    return "\n\n".join([*pieces, block])


def apply_science_general_audience_profile(store) -> int:
    """One-time operator-scoped migration that supersedes RC103 niche weighting."""
    with store.connect() as con:
        marker = con.execute(
            "SELECT value FROM meta WHERE key=?", (MIGRATION_KEY,)
        ).fetchone()
        if marker and str(marker[0] or "") == "1":
            return 0
        rows = con.execute(
            """SELECT c.id,p.selection_rules,p.rejection_rules,
                      p.selector_extra_prompt,p.writer_extra_prompt
               FROM channels c JOIN channel_policies p ON p.channel_id=c.id
               WHERE c.channel_mode='editorial'
                 AND c.editorial_runtime_profile='standard'
                 AND c.dedupe_profile='scientific_news'
                 AND c.dedupe_scientific_names=1
                 AND c.dedupe_compound_events=1"""
        ).fetchall()
        if not rows:
            return 0
        stamp = now_iso()
        for row in rows:
            cid = int(row["id"])
            con.execute(
                "UPDATE channels SET editorial_weights_json=?,updated_at=? WHERE id=?",
                (json.dumps(WEIGHTS, ensure_ascii=False, separators=(",", ":")), stamp, cid),
            )
            con.execute(
                """UPDATE channel_policies SET selection_rules=?,rejection_rules=?,
                         selector_extra_prompt=?,writer_extra_prompt=?,updated_at=?
                   WHERE channel_id=?""",
                (
                    _replace_old_block(row["selection_rules"], SELECTION),
                    _replace_old_block(row["rejection_rules"], REJECTION),
                    _replace_old_block(row["selector_extra_prompt"], SELECTOR),
                    _replace_old_block(row["writer_extra_prompt"], WRITER),
                    stamp, cid,
                ),
            )
        con.execute(
            "INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (MIGRATION_KEY, "1"),
        )
    event("editorial", "broad science audience channel migration", channels=len(rows), migration=MIGRATION_KEY)
    return len(rows)
