"""Fail closed on unreadable existing operator SQLite, recover hot journals normally."""
from __future__ import annotations
import sqlite3
from pathlib import Path

class ExistingDatabaseUnreadable(RuntimeError):
    """Preserve existing Data and request operator diagnosis, never re-import."""

def configured_channel_count(db_path: Path) -> int:
    """A writable SQLite open permits hot-journal recovery before channel probing."""
    db_path=Path(db_path)
    if not db_path.exists():
        return 0
    try:
        with sqlite3.connect(str(db_path),timeout=20) as con:
            con.execute("PRAGMA busy_timeout=20000")
            row=con.execute("SELECT COUNT(*) FROM channels").fetchone()
        return int(row[0] or 0) if row else 0
    except sqlite3.Error as exc:
        raise ExistingDatabaseUnreadable(
            "Наявна Data не відкрилася. Імпорт не потрібен і не буде запущений. "
            "Збережіть поточні Data та SQLite-журнали; закрийте інші копії Autopilot "
            "і перевірте доступ до диска. Причина SQLite: "+str(exc)
        ) from exc
