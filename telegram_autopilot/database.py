from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .models import Channel, CollectedArticle, Source
from .media import valid_public_media
from .paths import database_path


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def normalize_url(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
    except ValueError:
        return raw[:2000]
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}
    ]
    host = (parts.hostname or "").lower()
    netloc = host
    if parts.port and not ((parts.scheme == "http" and parts.port == 80) or (parts.scheme == "https" and parts.port == 443)):
        netloc += f":{parts.port}"
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), netloc, path, urlencode(query), ""))[:2000]


def content_hash(title: str, text: str) -> str:
    normalized = " ".join((title + "\n" + text).casefold().split())
    return hashlib.sha256(normalized.encode("utf-8", errors="ignore")).hexdigest()


class Database:
    def __init__(self, path: Path | None = None):
        self.path = path or database_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path, timeout=30)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
        try:
            yield con
            con.commit()
        finally:
            con.close()

    @staticmethod
    def _ensure_column(con: sqlite3.Connection, table: str, name: str, declaration: str) -> None:
        columns = {str(row[1]) for row in con.execute(f"PRAGMA table_info({table})").fetchall()}
        if name not in columns:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")

    def _init(self) -> None:
        with self.connect() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    telegram_chat_id TEXT NOT NULL,
                    editorial_profile TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    include_source_link INTEGER NOT NULL DEFAULT 0,
                    poll_interval_minutes INTEGER NOT NULL DEFAULT 5,
                    min_publish_interval_minutes INTEGER NOT NULL DEFAULT 10,
                    dedupe_window_hours INTEGER NOT NULL DEFAULT 72,
                    max_age_hours INTEGER NOT NULL DEFAULT 24,
                    max_posts_per_cycle INTEGER NOT NULL DEFAULT 3,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
                    kind TEXT NOT NULL,
                    name TEXT NOT NULL,
                    url TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    initialized INTEGER NOT NULL DEFAULT 0,
                    last_checked_at TEXT,
                    last_error TEXT,
                    UNIQUE(channel_id, url)
                );
                CREATE TABLE IF NOT EXISTS articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
                    source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
                    external_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL DEFAULT '',
                    normalized_url TEXT NOT NULL DEFAULT '',
                    raw_text TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    source_published_at TEXT,
                    discovered_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    language TEXT NOT NULL DEFAULT '',
                    reject_reason TEXT,
                    duplicate_of INTEGER REFERENCES articles(id),
                    event_key TEXT NOT NULL DEFAULT '',
                    event_summary TEXT NOT NULL DEFAULT '',
                    rewrite_text TEXT NOT NULL DEFAULT '',
                    ai_provider TEXT NOT NULL DEFAULT '',
                    ai_model TEXT NOT NULL DEFAULT '',
                    processing_started_at TEXT,
                    published_at TEXT,
                    telegram_message_id TEXT,
                    last_error TEXT,
                    media_json TEXT NOT NULL DEFAULT '[]',
                    headline_uk TEXT NOT NULL DEFAULT '',
                    teaser_text TEXT NOT NULL DEFAULT '',
                    full_article_uk TEXT NOT NULL DEFAULT '',
                    telegraph_url TEXT NOT NULL DEFAULT '',
                    telegraph_path TEXT NOT NULL DEFAULT '',
                    telegraph_created_at TEXT,
                    telegram_media_count INTEGER NOT NULL DEFAULT 0,
                    article_layout_json TEXT NOT NULL DEFAULT '',
                    media_captions_json TEXT NOT NULL DEFAULT '{}',
                    UNIQUE(channel_id, source_id, external_id)
                );
                CREATE INDEX IF NOT EXISTS idx_articles_channel_status ON articles(channel_id, status, discovered_at DESC);
                CREATE INDEX IF NOT EXISTS idx_articles_hash ON articles(channel_id, content_hash);
                CREATE INDEX IF NOT EXISTS idx_articles_url ON articles(channel_id, normalized_url);
                CREATE TABLE IF NOT EXISTS app_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            # RC1 -> RC2 migration. Keeping the old fields makes copied Data folders safe.
            for name, declaration in (
                ("media_json", "TEXT NOT NULL DEFAULT '[]'"),
                ("headline_uk", "TEXT NOT NULL DEFAULT ''"),
                ("teaser_text", "TEXT NOT NULL DEFAULT ''"),
                ("full_article_uk", "TEXT NOT NULL DEFAULT ''"),
                ("telegraph_url", "TEXT NOT NULL DEFAULT ''"),
                ("telegraph_path", "TEXT NOT NULL DEFAULT ''"),
                ("telegraph_created_at", "TEXT"),
                ("telegram_media_count", "INTEGER NOT NULL DEFAULT 0"),
                ("article_layout_json", "TEXT NOT NULL DEFAULT ''"),
                ("media_captions_json", "TEXT NOT NULL DEFAULT '{}'"),
            ):
                self._ensure_column(con, "articles", name, declaration)

    def quick_check(self) -> None:
        with self.connect() as con:
            row = con.execute("PRAGMA quick_check").fetchone()
            if not row or row[0] != "ok":
                raise RuntimeError("SQLite quick_check failed")

    def list_channels(self) -> list[Channel]:
        with self.connect() as con:
            rows = con.execute("SELECT * FROM channels ORDER BY name COLLATE NOCASE").fetchall()
        return [Channel(**{**dict(r), "enabled": bool(r["enabled"]), "include_source_link": bool(r["include_source_link"])}) for r in rows]

    def get_channel(self, channel_id: int) -> Channel | None:
        with self.connect() as con:
            row = con.execute("SELECT * FROM channels WHERE id=?", (channel_id,)).fetchone()
        if not row:
            return None
        return Channel(**{**dict(row), "enabled": bool(row["enabled"]), "include_source_link": bool(row["include_source_link"])})

    def save_channel(
        self,
        *,
        channel_id: int | None,
        name: str,
        telegram_chat_id: str,
        editorial_profile: str,
        enabled: bool,
        include_source_link: bool,
        poll_interval_minutes: int,
        min_publish_interval_minutes: int,
        dedupe_window_hours: int,
        max_age_hours: int,
        max_posts_per_cycle: int,
    ) -> int:
        stamp = now_iso()
        values = (
            name.strip(), telegram_chat_id.strip(), editorial_profile.strip(), int(enabled), int(include_source_link),
            max(1, int(poll_interval_minutes)), max(0, int(min_publish_interval_minutes)), max(1, int(dedupe_window_hours)),
            max(1, int(max_age_hours)), max(1, int(max_posts_per_cycle)), stamp,
        )
        with self.connect() as con:
            if channel_id:
                con.execute(
                    """UPDATE channels SET name=?,telegram_chat_id=?,editorial_profile=?,enabled=?,include_source_link=?,
                    poll_interval_minutes=?,min_publish_interval_minutes=?,dedupe_window_hours=?,max_age_hours=?,
                    max_posts_per_cycle=?,updated_at=? WHERE id=?""",
                    values + (channel_id,),
                )
                return channel_id
            cur = con.execute(
                """INSERT INTO channels(name,telegram_chat_id,editorial_profile,enabled,include_source_link,
                poll_interval_minutes,min_publish_interval_minutes,dedupe_window_hours,max_age_hours,max_posts_per_cycle,
                created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                values[:-1] + (stamp, stamp),
            )
            return int(cur.lastrowid)

    def delete_channel(self, channel_id: int) -> None:
        with self.connect() as con:
            con.execute("DELETE FROM channels WHERE id=?", (channel_id,))

    def list_sources(self, channel_id: int) -> list[Source]:
        with self.connect() as con:
            rows = con.execute("SELECT * FROM sources WHERE channel_id=? ORDER BY name COLLATE NOCASE", (channel_id,)).fetchall()
        return [Source(**{**dict(r), "enabled": bool(r["enabled"]), "initialized": bool(r["initialized"])}) for r in rows]

    def save_source(self, *, source_id: int | None, channel_id: int, kind: str, name: str, url: str, enabled: bool) -> int:
        with self.connect() as con:
            if source_id:
                old = con.execute("SELECT kind,url FROM sources WHERE id=? AND channel_id=?", (source_id, channel_id)).fetchone()
                reset = bool(old and (str(old["kind"]) != kind or str(old["url"]) != url.strip()))
                con.execute(
                    "UPDATE sources SET kind=?,name=?,url=?,enabled=?,initialized=CASE WHEN ? THEN 0 ELSE initialized END WHERE id=? AND channel_id=?",
                    (kind, name.strip(), url.strip(), int(enabled), int(reset), source_id, channel_id),
                )
                return source_id
            cur = con.execute(
                "INSERT INTO sources(channel_id,kind,name,url,enabled) VALUES(?,?,?,?,?)",
                (channel_id, kind, name.strip(), url.strip(), int(enabled)),
            )
            return int(cur.lastrowid)

    def delete_source(self, source_id: int) -> None:
        with self.connect() as con:
            con.execute("DELETE FROM sources WHERE id=?", (source_id,))

    def source_checked(self, source_id: int, *, initialized: bool | None = None, error: str | None = None) -> None:
        with self.connect() as con:
            if initialized is None:
                con.execute("UPDATE sources SET last_checked_at=?,last_error=? WHERE id=?", (now_iso(), error, source_id))
            else:
                con.execute(
                    "UPDATE sources SET last_checked_at=?,last_error=?,initialized=? WHERE id=?",
                    (now_iso(), error, int(initialized), source_id),
                )

    def insert_collected(self, source: Source, item: CollectedArticle, *, baseline: bool) -> int | None:
        h = content_hash(item.title, item.raw_text)
        nurl = normalize_url(item.url)
        status = "baseline" if baseline else "new"
        media_json = json.dumps(list(dict.fromkeys(item.media_urls))[:24], ensure_ascii=False)
        with self.connect() as con:
            try:
                cur = con.execute(
                    """INSERT INTO articles(channel_id,source_id,external_id,title,url,normalized_url,raw_text,content_hash,
                    source_published_at,discovered_at,status,media_json,article_layout_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        source.channel_id, source.id, item.external_id[:1000], item.title[:1000], item.url[:2000], nurl,
                        item.raw_text, h, item.published_at, now_iso(), status, media_json, item.article_layout_json or "",
                    ),
                )
            except sqlite3.IntegrityError:
                return None
            return int(cur.lastrowid)

    def get_article(self, article_id: int) -> sqlite3.Row | None:
        with self.connect() as con:
            return con.execute(
                "SELECT a.*,s.name AS source_name FROM articles a JOIN sources s ON s.id=a.source_id WHERE a.id=?",
                (article_id,),
            ).fetchone()

    def pending_articles(self, channel_id: int, limit: int = 20) -> list[sqlite3.Row]:
        with self.connect() as con:
            return con.execute(
                """SELECT a.*,s.name AS source_name FROM articles a JOIN sources s ON s.id=a.source_id
                WHERE a.channel_id=? AND a.status IN ('new','retry') ORDER BY a.id ASC LIMIT ?""",
                (channel_id, limit),
            ).fetchall()

    def recent_published(self, channel_id: int, hours: int, limit: int = 30) -> list[sqlite3.Row]:
        with self.connect() as con:
            return con.execute(
                """SELECT id,title,event_key,event_summary,headline_uk,teaser_text,full_article_uk,published_at,url FROM articles
                WHERE channel_id=? AND status='published' AND datetime(published_at) >= datetime('now', ?)
                ORDER BY published_at DESC LIMIT ?""",
                (channel_id, f"-{max(1, int(hours))} hours", limit),
            ).fetchall()

    def exact_duplicate(self, channel_id: int, article_id: int, normalized_url: str, h: str) -> int | None:
        with self.connect() as con:
            row = con.execute(
                """SELECT id FROM articles WHERE channel_id=? AND id<>? AND status='published'
                AND ((normalized_url<>'' AND normalized_url=?) OR content_hash=?) ORDER BY id DESC LIMIT 1""",
                (channel_id, article_id, normalized_url, h),
            ).fetchone()
        return int(row[0]) if row else None

    def update_article(self, article_id: int, **fields: object) -> None:
        allowed = {
            "status", "language", "reject_reason", "duplicate_of", "event_key", "event_summary", "rewrite_text",
            "headline_uk", "teaser_text", "full_article_uk", "telegraph_url", "telegraph_path", "telegraph_created_at",
            "telegram_media_count", "ai_provider", "ai_model", "processing_started_at", "published_at",
            "telegram_message_id", "last_error", "raw_text", "media_json", "article_layout_json",
            "media_captions_json", "content_hash",
        }
        pairs = [(k, v) for k, v in fields.items() if k in allowed]
        if not pairs:
            return
        sql = "UPDATE articles SET " + ",".join(f"{k}=?" for k, _ in pairs) + " WHERE id=?"
        with self.connect() as con:
            con.execute(sql, tuple(v for _, v in pairs) + (article_id,))

    def media_urls(self, row: sqlite3.Row) -> list[str]:
        try:
            raw = json.loads(str(row["media_json"] or "[]"))
        except Exception:
            return []
        if not isinstance(raw, list):
            return []
        result: list[str] = []
        for item in raw:
            value = str(item).strip()
            if valid_public_media(value) is not None and value not in result:
                result.append(value)
        return result[:24]

    def article_layout_json(self, row: sqlite3.Row) -> str:
        try:
            return str(row["article_layout_json"] or "")
        except Exception:
            return ""

    def media_captions(self, row: sqlite3.Row) -> dict[int, str]:
        try:
            raw = json.loads(str(row["media_captions_json"] or "{}"))
        except Exception:
            return {}
        if not isinstance(raw, dict):
            return {}
        result: dict[int, str] = {}
        for key, value in raw.items():
            try:
                idx = int(key)
            except (TypeError, ValueError):
                continue
            text = " ".join(str(value or "").split()).strip()
            if text:
                result[idx] = text[:1000]
        return result

    def last_published_at(self, channel_id: int) -> str | None:
        with self.connect() as con:
            row = con.execute("SELECT MAX(published_at) FROM articles WHERE channel_id=? AND status='published'", (channel_id,)).fetchone()
        return str(row[0]) if row and row[0] else None

    def history(self, channel_id: int | None = None, status: str | None = None, limit: int = 500) -> list[sqlite3.Row]:
        where, params = [], []
        if channel_id:
            where.append("a.channel_id=?"); params.append(channel_id)
        if status:
            where.append("a.status=?"); params.append(status)
        clause = " WHERE " + " AND ".join(where) if where else ""
        with self.connect() as con:
            return con.execute(
                f"""SELECT a.id,c.name channel_name,s.name source_name,a.title,a.headline_uk,a.status,a.reject_reason,a.discovered_at,
                a.published_at,a.ai_provider,a.telegram_message_id,a.telegraph_url,a.telegram_media_count,a.last_error FROM articles a
                JOIN channels c ON c.id=a.channel_id JOIN sources s ON s.id=a.source_id {clause}
                ORDER BY a.id DESC LIMIT ?""",
                tuple(params) + (limit,),
            ).fetchall()

    def get_state(self, key: str, default: str = "") -> str:
        with self.connect() as con:
            row = con.execute("SELECT value FROM app_state WHERE key=?", (key,)).fetchone()
        return str(row[0]) if row else default

    def set_state(self, key: str, value: str) -> None:
        with self.connect() as con:
            con.execute(
                "INSERT INTO app_state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, str(value)),
            )

    def stats(self, channel_id: int | None = None) -> dict[str, int]:
        params: tuple[object, ...] = (channel_id,) if channel_id else ()
        where = " WHERE channel_id=?" if channel_id else ""
        with self.connect() as con:
            rows = con.execute(f"SELECT status,COUNT(*) n FROM articles{where} GROUP BY status", params).fetchall()
        return {str(r[0]): int(r[1]) for r in rows}
