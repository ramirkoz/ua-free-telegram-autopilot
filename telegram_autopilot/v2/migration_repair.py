from __future__ import annotations

from .storage import now_iso

_POLL_MARKER = "rc90_poll_interval_15m_repair_v1"


def repair_polling_baseline(store) -> dict[str, object]:
    """Apply the 15-minute baseline once, after imported channels actually exist.

    RC89 put its migration marker into a newly-created empty schema. First-run
    import then copied old channel rows (including 5-minute polling) into that
    database, so the later repair saw the marker and skipped the real data.

    RC90 deliberately refuses to consume its marker while the channels table is
    empty. Once channel rows exist, values below 15 minutes are raised exactly
    once. After that, operator edits remain authoritative.
    """
    with store.connect() as con:
        row = con.execute("SELECT value FROM meta WHERE key=?", (_POLL_MARKER,)).fetchone()
        if row and str(row[0] or "") == "1":
            return {"repaired": False, "reason": "already_applied", "channels_changed": 0}

        total = int(con.execute("SELECT COUNT(*) FROM channels").fetchone()[0] or 0)
        if total <= 0:
            return {"repaired": False, "reason": "no_channels", "channels_changed": 0}

        changed = int(
            con.execute("SELECT COUNT(*) FROM channels WHERE poll_interval_minutes<15").fetchone()[0] or 0
        )
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
        }
