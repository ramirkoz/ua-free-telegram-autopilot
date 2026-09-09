from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

from .domain import BlockedBy, ChannelMode, Decision, MigrationReport, Stage
from .loghub import event
from .storage import V2Store, now_iso


RUNTIME_TABLE_HINTS = (
    "provider", "cooldown", "circuit", "runtime", "worker", "lease", "retry", "selector_cache", "repair",
)


def _columns(con: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {str(row[1]) for row in con.execute(f"PRAGMA table_info({table})")}
    except sqlite3.Error:
        return set()


def _tables(con: sqlite3.Connection) -> set[str]:
    return {str(row[0]) for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _pick(data: dict[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return default


def _bool(value: Any, default: bool = False) -> int:
    if value is None:
        return int(default)
    if isinstance(value, str):
        return int(value.strip().casefold() not in {"", "0", "false", "no", "off"})
    return int(bool(value))


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _dt(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def locate_legacy_database(path: str | Path) -> Path:
    src = Path(path)
    if src.is_file() and src.suffix.casefold() in {".sqlite3", ".sqlite", ".db"}:
        return src
    if src.is_dir():
        preferred = [src / "telegram_autopilot.sqlite3", src / "Data" / "telegram_autopilot.sqlite3"]
        for item in preferred:
            if item.exists():
                return item
        candidates = [p for p in src.rglob("*") if p.is_file() and p.suffix.casefold() in {".sqlite3", ".sqlite", ".db"}]
        if candidates:
            candidates.sort(key=lambda p: ("telegram_autopilot" not in p.name.casefold(), len(str(p))))
            return candidates[0]
    raise FileNotFoundError(f"Не знайдено стару SQLite Data у {src}")


def open_legacy_readonly(path: str | Path) -> sqlite3.Connection:
    db = locate_legacy_database(path).resolve()
    uri = "file:" + quote(str(db).replace("\\", "/"), safe="/:._-") + "?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    return con


def build_export_bundle(legacy_path: str | Path, output_zip: str | Path) -> Path:
    db = locate_legacy_database(legacy_path)
    output = Path(output_zip)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open_legacy_readonly(db) as con:
        tables = sorted(_tables(con))
        manifest: dict[str, Any] = {
            "format": "ua-free-autopilot-legacy-export-v1",
            "created_at": now_iso(),
            "source_database": db.name,
            "tables": {},
        }
        payload: dict[str, Any] = {}
        for table in tables:
            if table.startswith("sqlite_"):
                continue
            cols = sorted(_columns(con, table))
            manifest["tables"][table] = {"columns": cols, "count": int(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])}
            # Export user/editorial data and publication history. Runtime-only state is documented but omitted.
            low = table.casefold()
            if any(hint in low for hint in RUNTIME_TABLE_HINTS) and table not in {"articles"}:
                continue
            try:
                rows = con.execute(f"SELECT * FROM {table}").fetchall()
            except sqlite3.Error:
                continue
            payload[table] = [_row_dict(row) for row in rows]
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2, default=str))
        zf.writestr("data.json", json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str))
    event("migration", "legacy export bundle created", source=str(db), output=str(output))
    return output


def _legacy_mode(data: dict[str, Any]) -> str:
    raw = str(_pick(data, "channel_mode", "mode", "editorial_mode", default="editorial") or "editorial").casefold()
    return "monitoring" if raw.startswith("monitor") else "editorial"


def _legacy_language(data: dict[str, Any]) -> str:
    raw = str(_pick(data, "language_mode", "content_direction", "language_direction", "input_language_mode", default="") or "").strip()
    if raw:
        return raw
    # RC69/70 used content_direction in later generations; default safely accepts UA/RU and emits UA.
    return "ukru_to_uk"


def _canonical_url(data: dict[str, Any]) -> str:
    value = str(_pick(data, "canonical_source_url", "normalized_url", "url", default="") or "").strip()
    return value if value.startswith(("http://", "https://")) else ""


def _known_channel_fields() -> set[str]:
    return {
        "id","name","telegram_chat_id","enabled","channel_mode","mode","editorial_mode","editorial_profile","include_source_link",
        "poll_interval_minutes","poll_immediate","min_publish_interval_minutes","dedupe_window_hours","max_age_hours","max_posts_per_cycle",
        "publish_24h","publish_start","publish_end","publish_immediately","topic_balance_enabled","topic_daily_limit","related_spacing_posts",
        "editorial_weights_json","language_mode","content_direction","language_direction","input_language_mode","media_enrichment_mode",
        "media_first_allowed","media_min_text_chars","created_at","updated_at",
    }


def import_legacy_data(legacy_path: str | Path, store: V2Store, *, reevaluate_hours: int = 48) -> MigrationReport:
    db_path = locate_legacy_database(legacy_path)
    report = MigrationReport(source=str(db_path))
    report.skipped_runtime_state = [
        "AI provider cooldown/circuit state", "temporary provider errors", "worker/thread/lease state",
        "old retry schedule and repair queue", "selector caches", "runtime/version markers",
    ]
    event("migration", "legacy import started", source=str(db_path), target=str(store.path))

    with open_legacy_readonly(db_path) as old:
        tables = _tables(old)
        if "channels" not in tables or "sources" not in tables or "articles" not in tables:
            raise ValueError("Стара Data не містить обов'язкових таблиць channels/sources/articles")

        channels = old.execute("SELECT * FROM channels ORDER BY id").fetchall()
        sources = old.execute("SELECT * FROM sources ORDER BY id").fetchall()
        articles = old.execute("SELECT * FROM articles ORDER BY id").fetchall()
        report.channels_total = len(channels); report.sources_total = len(sources); report.articles_total = len(articles)

        policies: dict[int, dict[str, Any]] = {}
        if "channel_policies" in tables:
            for row in old.execute("SELECT * FROM channel_policies"):
                data = _row_dict(row); policies[_int(data.get("channel_id"),0)] = data

        with store.transaction() as new:
            try:
                new.execute("BEGIN IMMEDIATE")
                for row in channels:
                    d = _row_dict(row); cid = _int(d.get("id"),0)
                    extras = {k: v for k, v in d.items() if k not in _known_channel_fields()}
                    stamp = str(_pick(d,"updated_at","created_at",default=now_iso()) or now_iso())
                    new.execute(
                        """INSERT OR REPLACE INTO channels(
                           id,name,telegram_chat_id,enabled,channel_mode,editorial_profile,include_source_link,source_link_required,
                           poll_interval_minutes,poll_immediate,min_publish_interval_minutes,dedupe_window_hours,max_age_hours,max_posts_per_cycle,
                           publish_24h,publish_start,publish_end,publish_immediately,topic_balance_enabled,topic_daily_limit,related_spacing_posts,
                           editorial_weights_json,language_mode,media_enrichment_mode,media_first_allowed,media_min_text_chars,legacy_config_json,created_at,updated_at
                        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            cid,str(d.get("name") or f"Канал {cid}"),str(d.get("telegram_chat_id") or ""),_bool(d.get("enabled"),True),_legacy_mode(d),
                            str(d.get("editorial_profile") or ""),_bool(d.get("include_source_link"),True),1,
                            _int(d.get("poll_interval_minutes"),5),_bool(d.get("poll_immediate"),False),_int(d.get("min_publish_interval_minutes"),10),
                            _int(d.get("dedupe_window_hours"),72),_int(d.get("max_age_hours"),24),_int(d.get("max_posts_per_cycle"),3),
                            _bool(d.get("publish_24h"),False),str(d.get("publish_start") or "07:00"),str(d.get("publish_end") or "00:00"),_bool(d.get("publish_immediately"),False),
                            _bool(d.get("topic_balance_enabled"),True),_int(d.get("topic_daily_limit"),2),_int(d.get("related_spacing_posts"),5),
                            str(d.get("editorial_weights_json") or "[]"),_legacy_language(d),str(d.get("media_enrichment_mode") or "auto"),
                            _bool(d.get("media_first_allowed"),True),_int(d.get("media_min_text_chars"),500),json.dumps(extras,ensure_ascii=False,separators=(",",":"),default=str),
                            str(d.get("created_at") or stamp),stamp,
                        ),
                    )
                    p = policies.get(cid,{})
                    purpose = str(p.get("purpose") or d.get("editorial_profile") or "")
                    selection = str(p.get("selection_rules") or d.get("editorial_profile") or "")
                    new.execute(
                        """INSERT OR REPLACE INTO channel_policies(channel_id,enabled,purpose,audience,selection_rules,rejection_rules,writing_rules,style_rules,
                           positive_examples,negative_examples,extra_instructions,selector_extra_prompt,writer_extra_prompt,media_policy,target_min_chars,target_max_chars,updated_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (cid,_bool(p.get("enabled"),True),purpose,str(p.get("audience") or "Україномовна аудиторія каналу."),selection,
                         str(p.get("rejection_rules") or ""),str(p.get("writing_rules") or ""),str(p.get("style_rules") or ""),
                         str(p.get("positive_examples") or ""),str(p.get("negative_examples") or ""),str(p.get("extra_instructions") or ""),
                         str(p.get("selector_extra_prompt") or ""),str(p.get("writer_extra_prompt") or ""),str(p.get("media_policy") or "required"),
                         _int(p.get("target_min_chars"),300),_int(p.get("target_max_chars"),750),str(p.get("updated_at") or stamp)),
                    )
                    report.channels_imported += 1

                source_ids: set[int] = set()
                for row in sources:
                    d = _row_dict(row); sid = _int(d.get("id"),0); cid = _int(d.get("channel_id"),0)
                    if not sid or not cid:
                        continue
                    known = {"id","channel_id","kind","name","url","enabled","initialized","priority","last_checked_at","last_error"}
                    extras = {k:v for k,v in d.items() if k not in known}
                    new.execute(
                        """INSERT OR REPLACE INTO sources(id,channel_id,kind,name,url,enabled,initialized,priority,last_checked_at,last_error,legacy_config_json)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                        (sid,cid,str(d.get("kind") or "web"),str(d.get("name") or d.get("url") or f"Source {sid}"),str(d.get("url") or ""),
                         _bool(d.get("enabled"),True),_bool(d.get("initialized"),False),_int(d.get("priority"),100),str(d.get("last_checked_at") or ""),
                         str(d.get("last_error") or ""),json.dumps(extras,ensure_ascii=False,separators=(",",":"),default=str)),
                    )
                    source_ids.add(sid); report.sources_imported += 1

                article_id_map: dict[int,int] = {}
                recent_cutoff = datetime.now(timezone.utc) - timedelta(hours=max(1,int(reevaluate_hours)))
                for row in articles:
                    d = _row_dict(row); legacy_id = _int(d.get("id"),0); cid = _int(d.get("channel_id"),0); sid = _int(d.get("source_id"),0)
                    if sid not in source_ids or not cid:
                        report.warnings.append(f"article #{legacy_id}: source/channel missing; skipped")
                        continue
                    legacy_status = str(d.get("status") or "").casefold()
                    published = legacy_status == "published" or bool(str(d.get("published_at") or "").strip())
                    discovered = str(d.get("discovered_at") or now_iso())
                    article_dt = _dt(d.get("source_published_at")) or _dt(discovered)
                    recent_unpublished = (not published) and article_dt is not None and article_dt >= recent_cutoff
                    if published:
                        stage, decision, blocked = str(Stage.PUBLISHED), str(Decision.PUBLISH), str(BlockedBy.NONE)
                    elif recent_unpublished:
                        stage, decision, blocked = str(Stage.COLLECTED), str(Decision.PENDING), str(BlockedBy.NONE)
                        report.pending_reevaluation += 1
                    else:
                        stage, decision, blocked = str(Stage.ARCHIVED), str(Decision.PENDING), str(BlockedBy.NONE)
                        report.archived_unpublished += 1
                    canonical = _canonical_url(d)
                    known_article = {
                        "id","channel_id","source_id","external_id","title","url","normalized_url","canonical_source_url","raw_text","content_hash",
                        "source_published_at","discovered_at","status","language","reject_reason","duplicate_of","event_key","event_summary","rewrite_text",
                        "ai_provider","ai_model","processing_started_at","published_at","telegram_message_id","last_error","retry_count","next_retry_at","media_json",
                        "headline_uk","teaser_text","full_article_uk","telegram_media_count","article_layout_json","media_captions_json","editorial_category",
                        "editorial_value_score","tags_json","topic_major","topic_minor","ready_at",
                    }
                    extras = {k:v for k,v in d.items() if k not in known_article}
                    cur = new.execute(
                        """INSERT INTO articles(legacy_article_id,channel_id,source_id,external_id,title,source_url,canonical_source_url,raw_text,content_hash,
                           source_published_at,discovered_at,stage,decision,blocked_by,reject_reason,event_key,event_summary,editorial_category,editorial_value_score,
                           tags_json,topic_major,topic_minor,draft_text,final_text,ai_provider,ai_model,media_json,article_layout_json,ready_at,published_at,
                           telegram_message_id,telegram_media_count,legacy_status,legacy_config_json)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (legacy_id,cid,sid,str(d.get("external_id") or legacy_id),str(d.get("title") or ""),str(d.get("url") or ""),canonical,
                         str(d.get("raw_text") or ""),str(d.get("content_hash") or ""),str(d.get("source_published_at") or ""),discovered,stage,decision,blocked,
                         str(d.get("reject_reason") or "") if not recent_unpublished else "",str(d.get("event_key") or ""),str(d.get("event_summary") or ""),
                         str(d.get("editorial_category") or ""),d.get("editorial_value_score"),str(d.get("tags_json") or "{}"),str(d.get("topic_major") or ""),
                         str(d.get("topic_minor") or ""),str(d.get("rewrite_text") or ""),str(d.get("teaser_text") or d.get("full_article_uk") or "") if published else "",
                         str(d.get("ai_provider") or ""),str(d.get("ai_model") or ""),str(d.get("media_json") or "[]"),str(d.get("article_layout_json") or "{}"),
                         str(d.get("ready_at") or ""),str(d.get("published_at") or ""),str(d.get("telegram_message_id") or ""),_int(d.get("telegram_media_count"),0),
                         str(d.get("status") or ""),json.dumps(extras,ensure_ascii=False,separators=(",",":"),default=str)),
                    )
                    new_id = int(cur.lastrowid); article_id_map[legacy_id] = new_id
                    report.articles_imported += 1
                    if published: report.published_imported += 1
                    if recent_unpublished:
                        stamp = now_iso()
                        new.execute("INSERT INTO jobs(article_id,channel_id,job_type,state,priority,available_at,created_at,updated_at) VALUES(?,?,'process','QUEUED',20,?,?,?)", (new_id,cid,stamp,stamp,stamp))

                # Preserve duplicate links after all article IDs exist.
                if "duplicate_of" in _columns(old,"articles"):
                    for row in articles:
                        d = _row_dict(row); legacy_id=_int(d.get("id"),0); legacy_dup=_int(d.get("duplicate_of"),0)
                        if legacy_id in article_id_map and legacy_dup in article_id_map:
                            new.execute("UPDATE articles SET duplicate_of=? WHERE id=?", (article_id_map[legacy_dup],article_id_map[legacy_id]))

                feedback_table = next((name for name in ("article_feedback","feedback","reaction_feedback") if name in tables), "")
                if feedback_table:
                    for row in old.execute(f"SELECT * FROM {feedback_table}"):
                        d=_row_dict(row); old_aid=_int(_pick(d,"article_id","id",default=0),0); new_aid=article_id_map.get(old_aid)
                        if not new_aid: continue
                        cid=_int(d.get("channel_id"),0) or _int(new.execute("SELECT channel_id FROM articles WHERE id=?",(new_aid,)).fetchone()[0],0)
                        known={"article_id","id","channel_id","telegram_message_id","checked_at","published_at","views","forwards","replies","likes","dislikes","fires","other_reactions"}
                        extras={k:v for k,v in d.items() if k not in known}
                        new.execute(
                            """INSERT OR REPLACE INTO feedback(article_id,channel_id,telegram_message_id,checked_at,published_at,views,forwards,replies,likes,dislikes,fires,other_reactions,legacy_config_json)
                               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (new_aid,cid,str(d.get("telegram_message_id") or ""),str(d.get("checked_at") or ""),str(d.get("published_at") or ""),
                             _int(d.get("views"),0),_int(d.get("forwards"),0),_int(d.get("replies"),0),_int(d.get("likes"),0),_int(d.get("dislikes"),0),
                             _int(d.get("fires"),0),_int(d.get("other_reactions"),0),json.dumps(extras,ensure_ascii=False,separators=(",",":"),default=str)),
                        )
                        report.feedback_imported += 1
                new.commit()
            except Exception:
                new.rollback(); raise

    _validate_import(store, report)
    event("migration", "legacy import completed", **report.as_dict())
    return report


def _validate_import(store: V2Store, report: MigrationReport) -> None:
    with store.connect() as con:
        channel_count = int(con.execute("SELECT COUNT(*) FROM channels").fetchone()[0])
        source_count = int(con.execute("SELECT COUNT(*) FROM sources").fetchone()[0])
        article_count = int(con.execute("SELECT COUNT(*) FROM articles").fetchone()[0])
        published_count = int(con.execute("SELECT COUNT(*) FROM articles WHERE stage='PUBLISHED'").fetchone()[0])
        missing_policy = int(con.execute("SELECT COUNT(*) FROM channels c LEFT JOIN channel_policies p ON p.channel_id=c.id WHERE p.channel_id IS NULL").fetchone()[0])
        requeued_published = int(con.execute("SELECT COUNT(*) FROM jobs j JOIN articles a ON a.id=j.article_id WHERE a.stage='PUBLISHED' AND j.state<>'DONE'").fetchone()[0])
    if channel_count < report.channels_imported: report.warnings.append("V2 channel count lower than imported count")
    if source_count < report.sources_imported: report.warnings.append("V2 source count lower than imported count")
    if article_count < report.articles_imported: report.warnings.append("V2 article count lower than imported count")
    if published_count != report.published_imported: report.warnings.append(f"published mismatch: expected {report.published_imported}, got {published_count}")
    if missing_policy: report.warnings.append(f"{missing_policy} channels have no policy")
    if requeued_published: raise RuntimeError(f"Migration invariant failed: {requeued_published} published articles requeued")


def import_from_bundle(bundle_zip: str | Path, store: V2Store) -> MigrationReport:
    """Offline migration helper: validate/export bundle, then import its embedded JSON through a temporary legacy DB.

    The primary supported path is direct read-only SQLite import. Bundle import exists for moving Data between machines
    without giving V2 write access to the original folder.
    """
    bundle = Path(bundle_zip)
    with zipfile.ZipFile(bundle,"r") as zf:
        manifest=json.loads(zf.read("manifest.json").decode("utf-8")); data=json.loads(zf.read("data.json").decode("utf-8"))
    if manifest.get("format") != "ua-free-autopilot-legacy-export-v1":
        raise ValueError("Невідомий формат legacy export bundle")
    with tempfile.TemporaryDirectory(prefix="autopilot-v2-import-") as tmp:
        tempdb=Path(tmp)/"legacy.sqlite3"; con=sqlite3.connect(tempdb)
        try:
            # Recreate generic tables from manifest using TEXT columns. Values remain lossless enough for importer coercion.
            for table,info in manifest.get("tables",{}).items():
                rows=data.get(table)
                if rows is None: continue
                cols=list(info.get("columns") or [])
                if not cols: continue
                quoted=",".join('"'+str(c).replace('"','""')+'" TEXT' for c in cols)
                con.execute('CREATE TABLE "'+table.replace('"','""')+'" ('+quoted+')')
                marks=",".join("?" for _ in cols)
                for row in rows:
                    con.execute('INSERT INTO "'+table.replace('"','""')+'" VALUES('+marks+')', tuple(row.get(c) for c in cols))
            con.commit()
        finally:
            con.close()
        return import_legacy_data(tempdb,store)
