from __future__ import annotations

import json
import os
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tkinter as tk
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


def _parse_dt(value: str):
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _normalize_imported_active_state(db_path: Path) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    requeued = archived = published = 0
    store = V2Store(db_path)
    with store.connect() as con:
        published = int(con.execute("SELECT COUNT(*) FROM articles WHERE stage='PUBLISHED'").fetchone()[0] or 0)
        rows = con.execute(
            """SELECT a.id,a.channel_id,a.source_published_at,a.discovered_at,c.max_age_hours,c.max_posts_per_cycle
                 FROM articles a JOIN channels c ON c.id=a.channel_id
                WHERE a.stage<>'PUBLISHED'
                ORDER BY a.channel_id,COALESCE(NULLIF(a.source_published_at,''),a.discovered_at) DESC,a.id DESC"""
        ).fetchall()
        kept_per_channel: dict[int, int] = {}
        for row in rows:
            article_id = int(row["id"]); channel_id = int(row["channel_id"])
            age_base = _parse_dt(str(row["source_published_at"] or "")) or _parse_dt(str(row["discovered_at"] or ""))
            max_age = max(1, int(row["max_age_hours"] or 24))
            stale = age_base is not None and age_base < now - timedelta(hours=max_age)
            active_cap = max(12, min(36, max(1, int(row["max_posts_per_cycle"] or 1)) * 12))
            already_kept = kept_per_channel.get(channel_id, 0)
            backlog_excess = already_kept >= active_cap
            if stale or backlog_excess:
                reason = "MIGRATION_STALE" if stale else "MIGRATION_BACKLOG_ARCHIVED"
                detail = (
                    "Старий непублікований матеріал не перенесено в активну чергу поточної версії"
                    if stale else
                    f"Міграційний backlog обмежено до {active_cap} найсвіжіших матеріалів каналу; матеріал збережено в історії без AI-обробки"
                )
                con.execute(
                    """UPDATE articles SET stage='ARCHIVED',decision='REJECT',blocked_by='NONE',
                       reject_reason=?,status_detail=?,draft_text='',final_text='',ready_at='',last_error_code=?,last_error_detail='',next_retry_at=''
                       WHERE id=?""", (reason, detail, reason, article_id),
                )
                archived += 1
                continue
            kept_per_channel[channel_id] = already_kept + 1
            con.execute(
                """UPDATE articles SET stage='COLLECTED',decision='PENDING',blocked_by='NONE',reject_reason='',status_detail='',
                   duplicate_of=NULL,event_key='',event_summary='',editorial_category='',editorial_value_score=NULL,tags_json='[]',
                   topic_major='',topic_minor='',draft_text='',final_text='',ai_provider='',ai_model='',ready_at='',
                   last_error_code='',last_error_detail='',retry_count=0,next_retry_at='' WHERE id=?""",
                (article_id,),
            )
            requeued += 1
            stamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
            con.execute(
                """INSERT INTO jobs(article_id,channel_id,job_type,state,priority,available_at,created_at,updated_at)
                   VALUES(?,?,'process','QUEUED',10,?,?,?)
                   ON CONFLICT(article_id,job_type) DO UPDATE SET state='QUEUED',priority=10,available_at=excluded.available_at,
                       lease_owner='',lease_until='',attempts=0,error_code='',error_detail='',updated_at=excluded.updated_at""",
                (article_id, channel_id, stamp, stamp, stamp),
            )
    return {"published_preserved": published, "active_requeued": requeued, "stale_archived": archived}


def _selective_import(source_db: Path, target_db: Path) -> dict[str, int]:
    temp = target_db.with_name(target_db.name + ".clean-import.tmp")
    temp.unlink(missing_ok=True)
    V2Store(temp)  # current clean schema only
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
        # Preserve only completed Facebook repost history, never old retry queues.
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
        dst.close(); src.close()
    os.replace(temp, target_db)
    counts.update(_normalize_imported_active_state(target_db))
    return counts




def _read_json_file(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return dict(value) if isinstance(value, dict) else {}
    except Exception:
        return {}


def _migrate_supervisor_durable_state(source_data: Path, target_data: Path) -> dict[str, object]:
    """Copy only durable observability settings, never old runtime/incident state.

    We preserve the operator's mirror folder and the private Telegram report target,
    because losing either makes a clean migration look healthy locally while remote
    observability silently disappears.
    """
    result: dict[str, object] = {"config": False, "telegram_target": False}
    source_supervisor = source_data / "supervisor"
    target_supervisor = target_data / "supervisor"
    target_supervisor.mkdir(parents=True, exist_ok=True)

    old_cfg = _read_json_file(source_supervisor / "config.json")
    if old_cfg:
        allowed = {
            "enabled", "mirror_dir", "interval_seconds", "ai_grace_seconds",
            "worker_stale_seconds", "queue_stall_seconds", "disk_min_free_mb",
        }
        clean = {k: old_cfg[k] for k in allowed if k in old_cfg}
        if clean:
            (target_supervisor / "config.json").write_text(
                json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            result["config"] = True

    candidates = [
        source_supervisor / "local_reports" / "telegram_target.json",
        source_supervisor / "agent" / "agent_telegram_target.json",
    ]
    chat_id = ""
    source_label = ""
    for candidate in candidates:
        value = str(_read_json_file(candidate).get("chat_id") or "").strip()
        if value:
            chat_id = value
            source_label = candidate.name
            break
    if not chat_id:
        for candidate in (
            source_supervisor / "local_reports" / "state.json",
            source_supervisor / "agent" / "agent_telegram_bridge_state.json",
        ):
            value = str(_read_json_file(candidate).get("resolved_chat_id") or "").strip()
            if value:
                chat_id = value
                source_label = candidate.name
                break

    # RC79-RC83 clean migrations may already have dropped the report target. If
    # the selected Data has none, inspect sibling historical Autopilot folders and
    # recover it only when they all agree on one unique private chat id.
    if not chat_id:
        siblings_root = source_data.parent.parent
        discovered: dict[str, str] = {}
        try:
            candidates_roots = [
                item / "Data" / "supervisor"
                for item in siblings_root.iterdir()
                if item.is_dir() and item.name.casefold().startswith("ua_free_telegram_autopilot")
            ]
        except Exception:
            candidates_roots = []
        for sup in candidates_roots:
            for candidate, key in (
                (sup / "local_reports" / "telegram_target.json", "chat_id"),
                (sup / "agent" / "agent_telegram_target.json", "chat_id"),
                (sup / "local_reports" / "state.json", "resolved_chat_id"),
                (sup / "agent" / "agent_telegram_bridge_state.json", "resolved_chat_id"),
            ):
                value = str(_read_json_file(candidate).get(key) or "").strip()
                if value:
                    discovered.setdefault(value, str(candidate))
        if len(discovered) == 1:
            chat_id, source_label = next(iter(discovered.items()))
            source_label = "sibling:" + Path(source_label).name

    if chat_id:
        target = target_supervisor / "local_reports" / "telegram_target.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps({"chat_id": chat_id, "source": f"migration:{source_label}"}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        result["telegram_target"] = True
    return result


def maybe_import_legacy_data(root) -> dict[str, object]:
    target = data_dir()
    marker = target / _MARKER
    target_db = target / "telegram_autopilot_v2.sqlite3"
    if marker.exists() or target_db.exists():
        return {"imported": False, "reason": "already_initialized"}

    if str(os.environ.get("UA_FREE_AUTOPILOT_SKIP_FIRST_RUN_IMPORT") or "").strip() == "1":
        marker.write_text(
            json.dumps(
                {"imported": False, "skipped": True, "reason": "noninteractive_first_run", "at": datetime.now(timezone.utc).isoformat()},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return {"imported": False, "reason": "noninteractive_first_run"}

    try:
        wants = messagebox.askyesno(
            "UA FREE Telegram Autopilot · перший запуск",
            "Імпортувати потрібні дані з попередньої версії?\n\n"
            "Перенесемо канали, джерела, правила, PUBLISHED-історію, навчання та credentials. "
            "Найсвіжіші непубліковані матеріали попередньої версії будуть переоброблені з нуля поточними правилами; великий старий backlog не спалюватиме AI-квоту.\n\n"
            "НЕ переносяться jobs, provider/source health, cooldown, audit, logs, cache, Tools/JRE/LanguageTool/Codex.",
            parent=root,
        )
    except Exception:
        wants = False
    if not wants:
        marker.write_text(json.dumps({"imported": False, "skipped": True, "at": datetime.now(timezone.utc).isoformat()}, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"imported": False, "reason": "skipped"}

    selected = filedialog.askdirectory(title="Виберіть стару папку Autopilot або її Data", parent=root)
    if not selected:
        return {"imported": False, "reason": "cancelled"}

    progress = None
    try:
        try:
            progress = tk.Toplevel(root)
            progress.title("UA FREE Telegram Autopilot · імпорт")
            progress.geometry("620x150")
            progress.resizable(False, False)
            progress.transient(root)
            frame = tk.Frame(progress, padx=18, pady=18)
            frame.pack(fill="both", expand=True)
            tk.Label(frame, text="Імпортую потрібні дані зі старої версії…", font=("TkDefaultFont", 11, "bold")).pack(anchor="w")
            tk.Label(
                frame,
                text="Це може тривати кілька хвилин на великій базі. Не запускайте другу копію програми.\n"
                     "Стара Data читається тільки на читання; логи/cache/Tools не переносяться.",
                justify="left", wraplength=570,
            ).pack(anchor="w", pady=(10, 0))
            progress.update_idletasks()
            progress.update()
        except Exception:
            progress = None
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
        supervisor_state = _migrate_supervisor_durable_state(source_data, target)
        payload = {
            "imported": True,
            "source": str(source_data),
            "tables": counts,
            "files": copied,
            "supervisor": supervisor_state,
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
            f"PUBLISHED збережено: {counts.get('published_preserved', 0)}\n"
            f"Свіжі непубліковані переобробити: {counts.get('active_requeued', 0)}\n"
            f"Старі/надлишкові непубліковані архівовано: {counts.get('stale_archived', 0)}\n"
            f"Credentials: {len(copied)} файли.\n"
            f"Supervisor mirror: {'так' if supervisor_state.get('config') else 'новий'}\n"
            f"Telegram report target: {'перенесено' if supervisor_state.get('telegram_target') else 'не знайдено'}\n\n"
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
    finally:
        if progress is not None:
            try:
                progress.destroy()
            except Exception:
                pass
