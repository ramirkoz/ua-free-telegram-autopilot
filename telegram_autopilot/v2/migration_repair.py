from __future__ import annotations


from .domain import ChannelMode
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

# Existing sources are configuration, not editorial core.  RC98 only changes the
# persisted source mix of channels that explicitly use the commercial-editorial
# profile. Unknown/custom sources are left untouched.
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
    """RC101 safety freeze: never rewrite operator channel policy during migration/startup.

    RC98 mixed schema repair with editorial seed content and source-name rules. Those
    values are operator configuration, so startup repair now only records the marker.
    Existing persisted settings are left byte-for-byte untouched; a future profile
    template may be applied explicitly from the UI after preview.
    """
    row = con.execute("SELECT value FROM meta WHERE key=?", (_PRODANO_PROFILE_MARKER,)).fetchone()
    if row and str(row[0] or "") == "1":
        return {"channels": 0, "sources_disabled": 0, "sources_prioritized": 0}
    con.execute(
        "INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (_PRODANO_PROFILE_MARKER, "1"),
    )
    return {"channels": 0, "sources_disabled": 0, "sources_prioritized": 0}


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
