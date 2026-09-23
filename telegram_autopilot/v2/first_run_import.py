from __future__ import annotations

import json
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from tkinter import filedialog, messagebox

from ..paths import data_dir
from .storage import V2Store

_MARKER = "first_run_import.json"
_SECRET_FILES = ("secrets.key", "secrets.secure")
_STABLE_TABLES = (
    "channels",
    "channel_policies",
    "sources",
    "articles",
    "feedback",
    "feedback_editor_reactions",
)


def _locate_data_folder(selected: Path) -> Path:
    selected = selected.resolve()
    if (selected / "telegram_autopilot_v2.sqlite3").is_file():
        return selected
    nested = selected / "Data"
    if (nested / "telegram_autopilot_v2.sqlite3").is_file():
        return nested
    raise FileNotFoundError("Не знайдено Data\\telegram_autopilot_v2.sqlite3")


def _columns(con: sqlite3.Connection, table: str) -> list[str]:
    try:
        return [str(row[1]) for row in con.execute(f'PRAGMA table_info("{table}")')]
    except sqlite3.Error:
        return []


def _copy_table(src: sqlite3.Connection, dst: sqlite3.Connection, table: str) -> int:
    src_cols = _columns(src, table)
    dst_cols = set(_columns(dst, table))
    cols = [name for name in src_cols if name in dst_cols]
    if not cols:
        return 0
    quoted = ",".join('"' + name.replace('"', '""') + '"' for name in cols)
    rows = src.execute(f'SELECT {quoted} FROM "{table}"').fetchall()
    if not rows:
        return 0
    marks = ",".join("?" for _ in cols)
    dst.executemany(
        f'INSERT OR REPLACE INTO "{table}" ({quoted}) VALUES ({marks})',
        [tuple(row) for row in rows],
    )
    return len(rows)


def _selective_import(source_db: Path, target_db: Path) -> dict[str, int]:
    temp = target_db.with_name(target_db.name + ".clean-import.tmp")
    temp.unlink(missing_ok=True)
    V2Store(temp)
    src = sqlite3.connect(f"file:{source_db.resolve().as_posix()}?mode=ro", uri=True, timeout=30)
    dst = sqlite3.connect(temp, timeout=30)
    counts: dict[str, int] = {}
    try:
        src.execute("PRAGMA query_only=ON")
        dst.execute("PRAGMA foreign_keys=OFF")
        dst.execute("BEGIN IMMEDIATE")
        for table in _STABLE_TABLES:
            if _columns(src, table) and _columns(dst, table):
                counts[table] = _copy_table(src, dst, table)
        if _columns(src, "facebook_reposts") and _columns(dst, "facebook_reposts"):
            src_cols = _columns(src, "facebook_reposts")
            dst_cols = set(_columns(dst, "facebook_reposts"))
            cols = [name for name in src_cols if name in dst_cols]
            quoted = ",".join('"' + name.replace('"', '""') + '"' for name in cols)
            rows = src.execute(
                f'SELECT {quoted} FROM "facebook_reposts" WHERE UPPER(state) IN ("PUBLISHED","DONE","SUCCESS")'
            ).fetchall()
            if rows:
                marks = ",".join("?" for _ in cols)
                dst.executemany(
                    f'INSERT OR REPLACE INTO "facebook_reposts" ({quoted}) VALUES ({marks})',
                    [tuple(row) for row in rows],
                )
            counts["facebook_reposts"] = len(rows)
        dst.commit()
        row = dst.execute("PRAGMA quick_check").fetchone()
        if not row or str(row[0]).casefold() != "ok":
            raise RuntimeError(f"SQLite quick_check failed: {row!r}")
    except Exception:
        dst.rollback()
        raise
    finally:
        dst.close()
        src.close()
    os.replace(temp, target_db)
    return counts


def maybe_import_legacy_data(root) -> dict[str, object]:
    target = data_dir()
    marker = target / _MARKER
    target_db = target / "telegram_autopilot_v2.sqlite3"
    if marker.exists() or target_db.exists():
        return {"imported": False, "reason": "already_initialized"}

    try:
        wants = messagebox.askyesno(
            "UA FREE Telegram Autopilot · перший запуск",
            "Імпортувати потрібні дані з попередньої версії?\n\n"
            "Перенесемо канали, джерела, правила, історію матеріалів/публікацій, "
            "навчання та зашифровані credentials.\n\n"
            "НЕ переносяться jobs, provider/source health, cooldown, audit, logs, cache, Tools/JRE/LanguageTool/Codex.",
            parent=root,
        )
    except Exception:
        wants = False
    if not wants:
        marker.write_text(
            json.dumps(
                {"imported": False, "skipped": True, "at": datetime.now(timezone.utc).isoformat()},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return {"imported": False, "reason": "skipped"}

    selected = filedialog.askdirectory(title="Виберіть стару папку Autopilot або її Data", parent=root)
    if not selected:
        return {"imported": False, "reason": "cancelled"}

    try:
        source_data = _locate_data_folder(Path(selected))
        if source_data.resolve() == target.resolve():
            raise RuntimeError("Не можна імпортувати поточну Data у саму себе.")
        source_db = source_data / "telegram_autopilot_v2.sqlite3"
        counts = _selective_import(source_db, target_db)
        copied: list[str] = []
        for name in _SECRET_FILES:
            src = source_data / name
            if src.is_file():
                shutil.copy2(src, target / name)
                copied.append(name)
        payload = {
            "imported": True,
            "source": str(source_data),
            "tables": counts,
            "files": copied,
            "at": datetime.now(timezone.utc).isoformat(),
            "old_data_preserved": True,
        }
        marker.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        messagebox.showinfo(
            "Імпорт завершено",
            "Чиста Data створена.\n\n"
            f"Канали: {counts.get('channels', 0)}\n"
            f"Джерела: {counts.get('sources', 0)}\n"
            f"Матеріали/історія: {counts.get('articles', 0)}\n"
            f"Feedback: {counts.get('feedback', 0)}\n"
            f"Credentials: {len(copied)} файли.\n\n"
            "Стара Data не змінювалась.",
            parent=root,
        )
        return payload
    except Exception as exc:
        try:
            target_db.unlink(missing_ok=True)
        except Exception:
            pass
        messagebox.showerror("Імпорт не виконано", str(exc), parent=root)
        return {"imported": False, "reason": "error", "error": str(exc)}
