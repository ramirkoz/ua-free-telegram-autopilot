from __future__ import annotations

from .domain import ChannelMode
from .monitoring_live_now import install_monitoring_live_now_gate
from .storage import now_iso

_POLL_MARKER = "rc90_poll_interval_15m_repair_v1"
_LIVE_NOW_MARKER = "rc96_monitoring_live_now_policy_v1"
_LIVE_NOW_BLOCK = (
    "[LIVE_NOW_RC96]\n"
    "Не публікувати оперативні події, цінність яких існує лише прямо зараз або кілька хвилин: "
    "повітряна тривога/відбій/загроза; поточний рух, проліт, курс або напрямок БпЛА, ракет, "
    "авіації чи інших повітряних цілей (у т.ч. евфемізми на кшталт ‘мопед’); ‘зараз палає/горить’, "
    "‘щойно/тільки що пролетіло/побачили/зафіксували’. 15-хвилинний цикл робить такі повідомлення "
    "застарілими. Дозволені стійкі факти й наслідки після події: було атаковано, пошкоджено, відкрили, "
    "побудували, знайшли, а також майбутні заплановані зміни на кшталт ‘завтра змінять маршрут’."
)


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


def repair_polling_baseline(store) -> dict[str, object]:
    """Apply 15-minute polling and seed visible live-now policy after import."""
    install_monitoring_live_now_gate()
    with store.connect() as con:
        live_now_changed = _repair_monitoring_live_now_policy(con)
        row = con.execute("SELECT value FROM meta WHERE key=?", (_POLL_MARKER,)).fetchone()
        if row and str(row[0] or "") == "1":
            return {
                "repaired": bool(live_now_changed),
                "reason": "already_applied",
                "channels_changed": 0,
                "live_now_channels_changed": live_now_changed,
            }

        total = int(con.execute("SELECT COUNT(*) FROM channels").fetchone()[0] or 0)
        if total <= 0:
            return {
                "repaired": bool(live_now_changed),
                "reason": "no_channels",
                "channels_changed": 0,
                "live_now_channels_changed": live_now_changed,
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
            "repaired": bool(changed or live_now_changed),
            "reason": "baseline_applied",
            "channels_changed": changed,
            "channels_total": total,
            "live_now_channels_changed": live_now_changed,
        }
