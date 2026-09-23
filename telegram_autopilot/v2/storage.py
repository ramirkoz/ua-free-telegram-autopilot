from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Iterator, Mapping

from . import V2_SCHEMA_VERSION
from ..media import encode_media, media_identity, valid_public_media
from .domain import AIModelHealth, BlockedBy, ChannelConfig, ChannelMode, ChannelPolicy, Decision, DedupeProfile, EditorialRuntimeProfile, ProviderHealth, ProviderState, SourceAttributionMode, SourceBodyAttributionMode, Stage
from .urlnorm import normalize_url




def _clean_media_json(value: str, *, limit: int = 24) -> str:
    try:
        parsed = json.loads(str(value or "[]"))
    except Exception:
        parsed = []
    values = [str(x) for x in parsed if str(x).strip()] if isinstance(parsed, list) else []
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        media = valid_public_media(value)
        if not media:
            continue
        kind, url = media
        key = media_identity(kind, url)
        if key in seen:
            continue
        seen.add(key)
        out.append(encode_media(kind, url))
        if len(out) >= max(1, int(limit)):
            break
    return json.dumps(out, ensure_ascii=False, separators=(",", ":"))


def _layout_source_kind(value: str) -> str:
    try:
        parsed = json.loads(str(value or "{}"))
    except Exception:
        return ""
    return str(parsed.get("source_kind") or "").strip().casefold() if isinstance(parsed, dict) else ""


def _telegram_media_filter_version(value: str) -> int:
    try:
        parsed=json.loads(str(value or "{}"))
        tg=parsed.get("telegram") if isinstance(parsed,dict) else None
        return int(tg.get("media_filter_version") or 0) if isinstance(tg,dict) else 0
    except Exception:
        return 0


def _media_json_count(value: str) -> int:
    try:
        parsed = json.loads(str(value or "[]"))
    except Exception:
        return 0
    return len(parsed) if isinstance(parsed, list) else 0


def _telegram_video_recovery(value: str) -> str:
    try:
        parsed = json.loads(str(value or "{}"))
        tg = parsed.get("telegram") if isinstance(parsed, dict) else None
        return str(tg.get("video_recovery") or "").strip().casefold() if isinstance(tg, dict) else ""
    except Exception:
        return ""


def _media_json_has_video(value: str) -> bool:
    try:
        parsed = json.loads(str(value or "[]"))
    except Exception:
        parsed = []
    if not isinstance(parsed, list):
        return False
    for raw in parsed:
        media = valid_public_media(str(raw or ""))
        if media and str(media[0]).casefold() == "video":
            return True
    return False


def _parse_datetime_value(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        try:
            dt = parsedate_to_datetime(raw)
        except Exception:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _normalize_datetime_value(value: str) -> str:
    dt = _parse_datetime_value(value)
    return dt.astimezone().isoformat(timespec="seconds") if dt is not None else str(value or "")


def _merge_media_json(old_value: str, new_value: str, *, limit: int = 24) -> str:
    values: list[str] = []
    for raw in (old_value, new_value):
        try:
            parsed = json.loads(str(raw or "[]"))
        except Exception:
            parsed = []
        if isinstance(parsed, list):
            values.extend(str(x) for x in parsed if str(x).strip())
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        parsed = valid_public_media(value)
        if not parsed:
            continue
        kind, url = parsed
        key = media_identity(kind, url)
        if key in seen:
            continue
        seen.add(key)
        out.append(encode_media(kind, url))
        if len(out) >= max(1, int(limit)):
            break
    return json.dumps(out, ensure_ascii=False, separators=(",", ":"))


def _refresh_layout(old_value: str, new_value: str) -> str:
    """Prefer the newest ingest layout while preserving restart-safe delivery state."""
    try:
        old = json.loads(str(old_value or "{}"))
    except Exception:
        old = {}
    try:
        new = json.loads(str(new_value or "{}"))
    except Exception:
        new = {}
    if not isinstance(old, dict):
        old = {}
    if not isinstance(new, dict) or not new:
        return json.dumps(old, ensure_ascii=False, separators=(",", ":"))
    delivery = old.get("telegram_delivery")
    if isinstance(delivery, dict) and delivery:
        new["telegram_delivery"] = delivery
    return json.dumps(new, ensure_ascii=False, separators=(",", ":"))

def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().casefold() not in {"", "0", "false", "no", "off"}
    return bool(value)


def _row_get(row: Mapping[str, Any] | sqlite3.Row | None, key: str, default: Any = None) -> Any:
    if row is None:
        return default
    try:
        value = row[key]
    except Exception:
        return default
    return default if value is None else value


SCHEMA = r"""
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS channels (
 id INTEGER PRIMARY KEY,name TEXT NOT NULL,telegram_chat_id TEXT NOT NULL DEFAULT '',enabled INTEGER NOT NULL DEFAULT 1,
 channel_mode TEXT NOT NULL DEFAULT 'editorial',editorial_profile TEXT NOT NULL DEFAULT '',editorial_runtime_profile TEXT NOT NULL DEFAULT 'standard',include_source_link INTEGER NOT NULL DEFAULT 1,
 source_link_required INTEGER NOT NULL DEFAULT 1,source_attribution_mode TEXT NOT NULL DEFAULT 'standard',poll_interval_minutes INTEGER NOT NULL DEFAULT 5,poll_immediate INTEGER NOT NULL DEFAULT 0,
 min_publish_interval_minutes INTEGER NOT NULL DEFAULT 10,dedupe_window_hours INTEGER NOT NULL DEFAULT 72,
 dedupe_profile TEXT NOT NULL DEFAULT 'standard',dedupe_scientific_names INTEGER NOT NULL DEFAULT 0,dedupe_compound_events INTEGER NOT NULL DEFAULT 0,
 dedupe_rare_terms INTEGER NOT NULL DEFAULT 0,published_dedupe_window_hours INTEGER NOT NULL DEFAULT 168,max_age_hours INTEGER NOT NULL DEFAULT 24,
 max_posts_per_cycle INTEGER NOT NULL DEFAULT 3,publish_24h INTEGER NOT NULL DEFAULT 0,publish_start TEXT NOT NULL DEFAULT '07:00',
 publish_end TEXT NOT NULL DEFAULT '00:00',publish_immediately INTEGER NOT NULL DEFAULT 0,topic_balance_enabled INTEGER NOT NULL DEFAULT 1,
 topic_daily_limit INTEGER NOT NULL DEFAULT 2,related_spacing_posts INTEGER NOT NULL DEFAULT 5,editorial_weights_json TEXT NOT NULL DEFAULT '[]',
 editorial_thresholds_json TEXT NOT NULL DEFAULT '{}',output_starvation_enabled INTEGER NOT NULL DEFAULT 1,output_starvation_window_hours INTEGER NOT NULL DEFAULT 4,
 output_starvation_min_processed INTEGER NOT NULL DEFAULT 20,output_starvation_min_published INTEGER NOT NULL DEFAULT 1,
 page_prefer_feed INTEGER NOT NULL DEFAULT 0,page_candidate_scan_limit INTEGER NOT NULL DEFAULT 24,page_fetch_limit INTEGER NOT NULL DEFAULT 8,
 input_starvation_enabled INTEGER NOT NULL DEFAULT 1,input_starvation_min_seen INTEGER NOT NULL DEFAULT 40,input_starvation_cycles INTEGER NOT NULL DEFAULT 3,
 language_mode TEXT NOT NULL DEFAULT 'ukru_to_uk',media_enrichment_mode TEXT NOT NULL DEFAULT 'auto',media_first_allowed INTEGER NOT NULL DEFAULT 1,
 media_min_text_chars INTEGER NOT NULL DEFAULT 500,facebook_page_ids_json TEXT NOT NULL DEFAULT '[]',legacy_config_json TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL,updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS channel_policies (
 channel_id INTEGER PRIMARY KEY REFERENCES channels(id) ON DELETE CASCADE,enabled INTEGER NOT NULL DEFAULT 1,purpose TEXT NOT NULL DEFAULT '',
 audience TEXT NOT NULL DEFAULT '',selection_rules TEXT NOT NULL DEFAULT '',rejection_rules TEXT NOT NULL DEFAULT '',writing_rules TEXT NOT NULL DEFAULT '',
 style_rules TEXT NOT NULL DEFAULT '',positive_examples TEXT NOT NULL DEFAULT '',negative_examples TEXT NOT NULL DEFAULT '',extra_instructions TEXT NOT NULL DEFAULT '',
 selector_extra_prompt TEXT NOT NULL DEFAULT '',writer_extra_prompt TEXT NOT NULL DEFAULT '',source_body_attribution_mode TEXT NOT NULL DEFAULT 'footer_only',source_body_attribution_marker TEXT NOT NULL DEFAULT '',media_policy TEXT NOT NULL DEFAULT 'required',
 target_min_chars INTEGER NOT NULL DEFAULT 300,target_max_chars INTEGER NOT NULL DEFAULT 750,updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sources (
 id INTEGER PRIMARY KEY,channel_id INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,kind TEXT NOT NULL,name TEXT NOT NULL,url TEXT NOT NULL,
 enabled INTEGER NOT NULL DEFAULT 1,initialized INTEGER NOT NULL DEFAULT 0,priority INTEGER NOT NULL DEFAULT 100,last_checked_at TEXT NOT NULL DEFAULT '',
 last_error TEXT NOT NULL DEFAULT '',legacy_config_json TEXT NOT NULL DEFAULT '{}',UNIQUE(channel_id,url)
);
CREATE INDEX IF NOT EXISTS idx_sources_channel ON sources(channel_id,enabled,priority,id);
CREATE TABLE IF NOT EXISTS source_health (
 source_id INTEGER PRIMARY KEY REFERENCES sources(id) ON DELETE CASCADE,consecutive_failures INTEGER NOT NULL DEFAULT 0,
 cooldown_until TEXT NOT NULL DEFAULT '',last_duration_ms INTEGER NOT NULL DEFAULT 0,last_outcome TEXT NOT NULL DEFAULT '',
 last_error TEXT NOT NULL DEFAULT '',updated_at TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_source_health_cooldown ON source_health(cooldown_until);
CREATE TABLE IF NOT EXISTS articles (
 id INTEGER PRIMARY KEY AUTOINCREMENT,legacy_article_id INTEGER,channel_id INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
 source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,external_id TEXT NOT NULL DEFAULT '',title TEXT NOT NULL DEFAULT '',
 source_url TEXT NOT NULL DEFAULT '',canonical_source_url TEXT NOT NULL DEFAULT '',raw_text TEXT NOT NULL DEFAULT '',content_hash TEXT NOT NULL DEFAULT '',
 source_published_at TEXT NOT NULL DEFAULT '',discovered_at TEXT NOT NULL,stage TEXT NOT NULL DEFAULT 'COLLECTED',decision TEXT NOT NULL DEFAULT 'PENDING',
 blocked_by TEXT NOT NULL DEFAULT 'NONE',status_detail TEXT NOT NULL DEFAULT '',reject_reason TEXT NOT NULL DEFAULT '',duplicate_of INTEGER REFERENCES articles(id),
 event_key TEXT NOT NULL DEFAULT '',event_summary TEXT NOT NULL DEFAULT '',editorial_category TEXT NOT NULL DEFAULT '',editorial_value_score INTEGER,
 tags_json TEXT NOT NULL DEFAULT '{}',topic_major TEXT NOT NULL DEFAULT '',topic_minor TEXT NOT NULL DEFAULT '',draft_text TEXT NOT NULL DEFAULT '',
 final_text TEXT NOT NULL DEFAULT '',ai_provider TEXT NOT NULL DEFAULT '',ai_model TEXT NOT NULL DEFAULT '',media_json TEXT NOT NULL DEFAULT '[]',
 article_layout_json TEXT NOT NULL DEFAULT '{}',ready_at TEXT NOT NULL DEFAULT '',published_at TEXT NOT NULL DEFAULT '',telegram_message_id TEXT NOT NULL DEFAULT '',
 telegram_media_count INTEGER NOT NULL DEFAULT 0,last_error_code TEXT NOT NULL DEFAULT '',last_error_detail TEXT NOT NULL DEFAULT '',retry_count INTEGER NOT NULL DEFAULT 0,
 next_retry_at TEXT NOT NULL DEFAULT '',legacy_status TEXT NOT NULL DEFAULT '',legacy_config_json TEXT NOT NULL DEFAULT '{}',UNIQUE(channel_id,source_id,external_id)
);
CREATE INDEX IF NOT EXISTS idx_articles_work ON articles(channel_id,decision,blocked_by,stage,id DESC);
CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(channel_id,published_at DESC,id DESC);
CREATE INDEX IF NOT EXISTS idx_articles_url ON articles(channel_id,canonical_source_url);
CREATE INDEX IF NOT EXISTS idx_articles_hash ON articles(channel_id,content_hash);
CREATE TABLE IF NOT EXISTS jobs (
 id INTEGER PRIMARY KEY AUTOINCREMENT,article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,channel_id INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
 job_type TEXT NOT NULL DEFAULT 'process',state TEXT NOT NULL DEFAULT 'QUEUED',priority INTEGER NOT NULL DEFAULT 100,available_at TEXT NOT NULL,
 lease_owner TEXT NOT NULL DEFAULT '',lease_until TEXT NOT NULL DEFAULT '',attempts INTEGER NOT NULL DEFAULT 0,error_code TEXT NOT NULL DEFAULT '',
 error_detail TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(article_id,job_type)
);
CREATE INDEX IF NOT EXISTS idx_jobs_ready ON jobs(state,available_at,priority,id);
CREATE INDEX IF NOT EXISTS idx_jobs_channel ON jobs(channel_id,state,priority,id);
CREATE TABLE IF NOT EXISTS provider_health (
 provider TEXT PRIMARY KEY,state TEXT NOT NULL DEFAULT 'UNKNOWN',model TEXT NOT NULL DEFAULT '',detail TEXT NOT NULL DEFAULT '',consecutive_failures INTEGER NOT NULL DEFAULT 0,
 success_count INTEGER NOT NULL DEFAULT 0,failure_count INTEGER NOT NULL DEFAULT 0,cooldown_until TEXT NOT NULL DEFAULT '',updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ai_model_health (
 provider TEXT NOT NULL,model TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'UNKNOWN',detail TEXT NOT NULL DEFAULT '',consecutive_failures INTEGER NOT NULL DEFAULT 0,
 success_count INTEGER NOT NULL DEFAULT 0,failure_count INTEGER NOT NULL DEFAULT 0,cooldown_until TEXT NOT NULL DEFAULT '',updated_at TEXT NOT NULL,
 PRIMARY KEY(provider,model)
);
CREATE INDEX IF NOT EXISTS idx_ai_model_health_provider ON ai_model_health(provider,state,updated_at DESC);
CREATE TABLE IF NOT EXISTS feedback (
 article_id INTEGER PRIMARY KEY REFERENCES articles(id) ON DELETE CASCADE,channel_id INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
 telegram_message_id TEXT NOT NULL DEFAULT '',checked_at TEXT NOT NULL DEFAULT '',published_at TEXT NOT NULL DEFAULT '',views INTEGER NOT NULL DEFAULT 0,
 forwards INTEGER NOT NULL DEFAULT 0,replies INTEGER NOT NULL DEFAULT 0,likes INTEGER NOT NULL DEFAULT 0,dislikes INTEGER NOT NULL DEFAULT 0,
 fires INTEGER NOT NULL DEFAULT 0,other_reactions INTEGER NOT NULL DEFAULT 0,
 editor_admin_count INTEGER NOT NULL DEFAULT 0,editor_reacted_count INTEGER NOT NULL DEFAULT 0,editor_coverage TEXT NOT NULL DEFAULT 'legacy',
 reactor_scan_complete INTEGER NOT NULL DEFAULT 0,reactor_scanned INTEGER NOT NULL DEFAULT 0,audience_reactions_json TEXT NOT NULL DEFAULT '{}',
 audience_total INTEGER NOT NULL DEFAULT 0,audience_positive INTEGER NOT NULL DEFAULT 0,audience_negative INTEGER NOT NULL DEFAULT 0,
 audience_fires INTEGER NOT NULL DEFAULT 0,audience_other INTEGER NOT NULL DEFAULT 0,legacy_config_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_feedback_channel ON feedback(channel_id,published_at DESC);
CREATE TABLE IF NOT EXISTS feedback_editor_reactions (
 article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,channel_id INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
 telegram_message_id TEXT NOT NULL,admin_peer_id TEXT NOT NULL,admin_name TEXT NOT NULL DEFAULT '',checked_at TEXT NOT NULL,
 likes INTEGER NOT NULL DEFAULT 0,dislikes INTEGER NOT NULL DEFAULT 0,fires INTEGER NOT NULL DEFAULT 0,other_reactions_json TEXT NOT NULL DEFAULT '{}',
 PRIMARY KEY(article_id,admin_peer_id)
);
CREATE INDEX IF NOT EXISTS idx_feedback_editor_channel_checked ON feedback_editor_reactions(channel_id,checked_at DESC);
CREATE TABLE IF NOT EXISTS facebook_reposts (
 article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,channel_id INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
 page_id TEXT NOT NULL,telegram_message_id TEXT NOT NULL DEFAULT '',telegram_post_url TEXT NOT NULL DEFAULT '',state TEXT NOT NULL DEFAULT 'PENDING',
 attempts INTEGER NOT NULL DEFAULT 0,next_retry_at TEXT NOT NULL DEFAULT '',facebook_post_id TEXT NOT NULL DEFAULT '',last_error TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(article_id,page_id)
);
CREATE INDEX IF NOT EXISTS idx_facebook_reposts_ready ON facebook_reposts(channel_id,state,next_retry_at,updated_at);
CREATE TABLE IF NOT EXISTS audit_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT,created_at TEXT NOT NULL,stream TEXT NOT NULL,event TEXT NOT NULL,channel_id INTEGER,article_id INTEGER,
 provider TEXT NOT NULL DEFAULT '',stage TEXT NOT NULL DEFAULT '',detail TEXT NOT NULL DEFAULT '',payload_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_audit_recent ON audit_events(created_at DESC,id DESC);
"""


class V2Store:
    def __init__(self, path: str | Path):
        self.path = Path(path); self.path.parent.mkdir(parents=True, exist_ok=True); self._init_lock = threading.Lock(); self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.path, timeout=30, isolation_level=None); con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON"); con.execute("PRAGMA busy_timeout=30000")
        try: yield con
        finally: con.close()

    def transaction(self) -> sqlite3.Connection:
        con=sqlite3.connect(self.path,timeout=30); con.row_factory=sqlite3.Row; con.execute("PRAGMA foreign_keys=ON"); con.execute("PRAGMA busy_timeout=30000"); return con

    def initialize(self) -> None:
        with self._init_lock:
            with self.connect() as con:
                con.executescript(SCHEMA)
                self._ensure_source_attribution_mode(con)
                self._ensure_source_body_attribution_policy(con)
                self._ensure_facebook_channel_settings(con)
                self._ensure_channel_dedupe_settings(con)
                self._ensure_rc59_channel_runtime_settings(con)
                self._ensure_rc62_ingest_settings(con)
                self._ensure_rc66_operational_channel_tuning(con)
                self._ensure_rc69_commercial_broad_audience_policy(con)
                self._ensure_rc71_commercial_media_quality_policy(con)
                self._ensure_rc72_channel_policy_tuning(con)
                con.execute("INSERT INTO meta(key,value) VALUES('schema_version',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(str(V2_SCHEMA_VERSION),))

    @staticmethod
    def _ensure_source_attribution_mode(con: sqlite3.Connection) -> None:
        """Keep attribution as explicit channel data; never infer it from a name."""
        columns = {str(row[1]) for row in con.execute("PRAGMA table_info(channels)").fetchall()}
        if "source_attribution_mode" not in columns:
            con.execute("ALTER TABLE channels ADD COLUMN source_attribution_mode TEXT NOT NULL DEFAULT 'standard'")
        con.execute(
            "INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            ("rc62_source_attribution_explicit_v1", "1"),
        )

    @staticmethod
    def _ensure_facebook_channel_settings(con: sqlite3.Connection) -> None:
        """Persist only selected Facebook Page IDs per channel; tokens stay encrypted."""
        columns = {str(row[1]) for row in con.execute("PRAGMA table_info(channels)").fetchall()}
        if "facebook_page_ids_json" not in columns:
            con.execute("ALTER TABLE channels ADD COLUMN facebook_page_ids_json TEXT NOT NULL DEFAULT '[]'")
        con.execute(
            "INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            ("rc77_facebook_crosspost_schema_v1", "1"),
        )

    @staticmethod
    def _ensure_channel_dedupe_settings(con: sqlite3.Connection) -> None:
        """Ensure explicit per-channel dedupe fields without channel-name inference.

        Older releases used one-time name matching to guess profiles for production
        channels.  RC61 removes that policy leak completely: the runtime and schema
        migration know only persisted channel settings. Existing Data keeps its
        already-saved profile values unchanged.
        """
        columns = {str(row[1]) for row in con.execute("PRAGMA table_info(channels)").fetchall()}
        additions = {
            "editorial_runtime_profile": "TEXT NOT NULL DEFAULT 'standard'",
            "dedupe_profile": "TEXT NOT NULL DEFAULT 'standard'",
            "dedupe_scientific_names": "INTEGER NOT NULL DEFAULT 0",
            "dedupe_compound_events": "INTEGER NOT NULL DEFAULT 0",
            "dedupe_rare_terms": "INTEGER NOT NULL DEFAULT 0",
            "published_dedupe_window_hours": "INTEGER NOT NULL DEFAULT 168",
        }
        for name, ddl in additions.items():
            if name not in columns:
                con.execute(f"ALTER TABLE channels ADD COLUMN {name} {ddl}")

        key = "rc61_explicit_channel_dedupe_no_name_inference_v1"
        done = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        if done and str(done[0] or "") == "1":
            return

        # Preserve the historical 30-day published ledger for channels that already
        # existed, but do not assign any editorial/dedupe profile by channel name or ID.
        con.execute(
            """UPDATE channels SET published_dedupe_window_hours=?
               WHERE published_dedupe_window_hours<=168""",
            (24 * 30,),
        )
        con.execute(
            "INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, "1"),
        )

    @staticmethod
    def _ensure_rc59_channel_runtime_settings(con: sqlite3.Connection) -> None:
        """Add per-channel editorial/output controls without runtime channel-name rules."""
        columns = {str(row[1]) for row in con.execute("PRAGMA table_info(channels)").fetchall()}
        additions = {
            "editorial_thresholds_json": "TEXT NOT NULL DEFAULT '{}'",
            "output_starvation_enabled": "INTEGER NOT NULL DEFAULT 1",
            "output_starvation_window_hours": "INTEGER NOT NULL DEFAULT 4",
            "output_starvation_min_processed": "INTEGER NOT NULL DEFAULT 20",
            "output_starvation_min_published": "INTEGER NOT NULL DEFAULT 1",
        }
        for name, ddl in additions.items():
            if name not in columns:
                con.execute(f"ALTER TABLE channels ADD COLUMN {name} {ddl}")

        key = "rc59_explicit_editorial_starvation_settings_v1"
        done = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        if done and str(done[0] or "") == "1":
            return
        commercial = {
            "commercial_case_fit": 58, "commercial_case_score": 46,
            "commercial_transferability": 40, "commercial_anchor": 52,
            "creative_case_fit": 62, "creative_case_score": 44,
            "creative_execution": 62, "creative_anchor": 48,
            "mechanism_case_fit": 64, "mechanism_case_score": 42,
            "mechanism": 58, "mechanism_transferability": 44,
        }
        payload = json.dumps(commercial, ensure_ascii=False, separators=(",", ":"))
        con.execute(
            """UPDATE channels SET editorial_thresholds_json=?
               WHERE editorial_runtime_profile=?
                 AND (editorial_thresholds_json='' OR editorial_thresholds_json='{}')""",
            (payload, str(EditorialRuntimeProfile.COMMERCIAL_EDITORIAL)),
        )
        con.execute(
            "INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, "1"),
        )

    @staticmethod
    def _ensure_rc62_ingest_settings(con: sqlite3.Connection) -> None:
        """Add visible per-channel ingest controls; runtime stays channel-agnostic."""
        columns = {str(row[1]) for row in con.execute("PRAGMA table_info(channels)").fetchall()}
        additions = {
            "page_prefer_feed": "INTEGER NOT NULL DEFAULT 0",
            "page_candidate_scan_limit": "INTEGER NOT NULL DEFAULT 24",
            "page_fetch_limit": "INTEGER NOT NULL DEFAULT 8",
            "input_starvation_enabled": "INTEGER NOT NULL DEFAULT 1",
            "input_starvation_min_seen": "INTEGER NOT NULL DEFAULT 40",
            "input_starvation_cycles": "INTEGER NOT NULL DEFAULT 3",
        }
        for name, ddl in additions.items():
            if name not in columns:
                con.execute(f"ALTER TABLE channels ADD COLUMN {name} {ddl}")
        key = "rc62_ingest_settings_seed_v1"
        done = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        if done and str(done[0] or "") == "1":
            return
        # One-time data-driven seed: page-heavy channels get deeper feed-first discovery.
        # No channel IDs, names or editorial labels are consulted.
        for row in con.execute("SELECT id FROM channels").fetchall():
            cid = int(row["id"])
            counts = con.execute(
                "SELECT COUNT(*) AS total, SUM(CASE WHEN kind='page' THEN 1 ELSE 0 END) AS pages FROM sources WHERE channel_id=? AND enabled=1",
                (cid,),
            ).fetchone()
            total = int(counts["total"] or 0) if counts else 0
            pages = int(counts["pages"] or 0) if counts else 0
            if total >= 3 and pages * 2 >= total:
                con.execute(
                    "UPDATE channels SET page_prefer_feed=1,page_candidate_scan_limit=48,page_fetch_limit=16 WHERE id=?",
                    (cid,),
                )
        con.execute(
            "INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, "1"),
        )


    @staticmethod
    def _ensure_rc66_operational_channel_tuning(con: sqlite3.Connection) -> None:
        """One-time explicit channel-setting tune based on persisted roles, never names/IDs.

        Existing commercial-editorial and monitoring channels are the only rows touched.
        Every changed value is normal persisted channel/policy data and remains visible/editable
        in the channel settings UI. Future channels are not auto-tuned by this migration.
        """
        key = "rc66_operational_channel_tuning_v1"
        done = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        if done and str(done[0] or "") == "1":
            return

        # Commercial/editorial channels: prefer real source media when present but do
        # not hold an otherwise publishable story forever. For page-heavy source sets,
        # search somewhat deeper for fresh URLs while keeping hard bounded limits.
        commercial_rows = con.execute(
            "SELECT id FROM channels WHERE editorial_runtime_profile=?",
            (str(EditorialRuntimeProfile.COMMERCIAL_EDITORIAL),),
        ).fetchall()
        for row in commercial_rows:
            cid = int(row["id"])
            counts = con.execute(
                "SELECT COUNT(*) total, SUM(CASE WHEN kind='page' THEN 1 ELSE 0 END) pages FROM sources WHERE channel_id=? AND enabled=1",
                (cid,),
            ).fetchone()
            total = int(counts["total"] or 0) if counts else 0
            pages = int(counts["pages"] or 0) if counts else 0
            con.execute(
                """UPDATE channels SET
                       max_posts_per_cycle=MAX(max_posts_per_cycle,4),
                       output_starvation_enabled=1,output_starvation_window_hours=2,
                       output_starvation_min_processed=5,output_starvation_min_published=1,
                       input_starvation_enabled=1,input_starvation_min_seen=40,input_starvation_cycles=2
                   WHERE id=?""",
                (cid,),
            )
            if total >= 3 and pages * 2 >= total:
                con.execute(
                    """UPDATE channels SET page_prefer_feed=1,
                           page_candidate_scan_limit=MAX(page_candidate_scan_limit,72),
                           page_fetch_limit=MAX(page_fetch_limit,20) WHERE id=?""",
                    (cid,),
                )
            con.execute(
                "UPDATE channel_policies SET media_policy='preferred',updated_at=? WHERE channel_id=?",
                (now_iso(), cid),
            )

        # Monitoring channels: five-minute polling is still near-real-time but avoids
        # repeatedly re-reading hundreds of already-known Telegram items. Preserve
        # source media/albums when present, but allow exact text-only source posts.
        monitoring_rows = con.execute(
            "SELECT id FROM channels WHERE channel_mode=?",
            (str(ChannelMode.MONITORING),),
        ).fetchall()
        for row in monitoring_rows:
            cid = int(row["id"])
            counts = con.execute(
                "SELECT COUNT(*) total, SUM(CASE WHEN kind='page' THEN 1 ELSE 0 END) pages FROM sources WHERE channel_id=? AND enabled=1",
                (cid,),
            ).fetchone()
            total = int(counts["total"] or 0) if counts else 0
            pages = int(counts["pages"] or 0) if counts else 0
            con.execute(
                """UPDATE channels SET
                       poll_interval_minutes=MAX(poll_interval_minutes,5),
                       max_posts_per_cycle=MAX(max_posts_per_cycle,5),
                       output_starvation_enabled=1,output_starvation_window_hours=1,
                       output_starvation_min_processed=1,output_starvation_min_published=1,
                       input_starvation_enabled=1,input_starvation_min_seen=40,input_starvation_cycles=3
                   WHERE id=?""",
                (cid,),
            )
            if total >= 3 and pages * 2 >= total:
                con.execute(
                    """UPDATE channels SET page_prefer_feed=1,
                           page_candidate_scan_limit=MAX(page_candidate_scan_limit,64),
                           page_fetch_limit=MAX(page_fetch_limit,16) WHERE id=?""",
                    (cid,),
                )
            con.execute(
                "UPDATE channel_policies SET media_policy='preferred',updated_at=? WHERE channel_id=?",
                (now_iso(), cid),
            )

        con.execute(
            "INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, "1"),
        )

    @staticmethod
    def _ensure_rc69_commercial_broad_audience_policy(con: sqlite3.Connection) -> None:
        """Persist broad-audience commercial policy in visible channel settings.

        The runtime remains channel-name/ID agnostic. Only channels explicitly using
        the commercial_editorial profile receive this one-time visible policy seed,
        and users can edit every resulting rule/threshold in Channel Settings.
        """
        key = "rc69_commercial_broad_audience_policy_v1"
        done = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        if done and str(done[0] or "") == "1":
            return
        rows = con.execute(
            """SELECT c.id,c.editorial_thresholds_json,p.selection_rules,p.rejection_rules,
                      p.selector_extra_prompt,p.writer_extra_prompt
                 FROM channels c JOIN channel_policies p ON p.channel_id=c.id
                WHERE c.editorial_runtime_profile=?""",
            (str(EditorialRuntimeProfile.COMMERCIAL_EDITORIAL),),
        ).fetchall()
        selection_block = (
            "[BROAD_AUDIENCE_RC69]\n"
            "Пріоритет: історії, цікаві широкій аудиторії навіть без професійного інтересу до маркетингу. "
            "Включай незвичні продукти й ціни, бренди у попкультурі, вірусні явища, меми, колаборації, "
            "споживчу поведінку, технології у повсякденному житті, рекламні провокації, факапи, дивні продажі "
            "та культурні феномени з брендовим/комерційним кутом. Професійний кейс допустимий, але не є базовим форматом."
        )
        rejection_block = (
            "[BROAD_AUDIENCE_RC69]\n"
            "Відхиляй рутинні B2B/agency case study, галузеві звіти, award/campaign recap і матеріали, "
            "цінність яких зрозуміла лише маркетологу. Якщо звичайна людина не захоче дочитати або переказати "
            "історію без пояснення професійної користі, це слабкий матеріал."
        )
        selector_block = (
            "[BROAD_AUDIENCE_RC69] General-audience interest FIRST, marketing relevance SECOND. "
            "Не вимагай, щоб історія була навчальним маркетинговим кейсом. Оціни, чи є в ній людський сюжет, "
            "сюрприз, культурний сигнал, споживчий конфлікт, дивний продукт/ціна, viral/meme/pop-culture або "
            "брендова поведінка, якою захочеться поділитися."
        )
        writer_block = (
            "[BROAD_AUDIENCE_RC69] Пиши для розумної широкої аудиторії, не для маркетингової конференції. "
            "Починай з найцікавішого факту/конфлікту; мінімізуй trade jargon, не пояснюй 'урок для маркетологів', "
            "якщо він не потрібен для розуміння самої історії."
        )
        for row in rows:
            def add_once(value: str, block: str) -> str:
                base = str(value or "").strip()
                if "[BROAD_AUDIENCE_RC69]" in base:
                    return base
                return (base + "\n\n" + block).strip() if base else block
            try:
                thresholds = json.loads(str(row["editorial_thresholds_json"] or "{}"))
            except Exception:
                thresholds = {}
            if not isinstance(thresholds, dict):
                thresholds = {}
            defaults = {
                "broad_interest_fit": 54,
                "broad_interest_score": 50,
                "broad_general_interest": 58,
                "broad_retellability": 58,
                "broad_culture_or_surprise": 55,
            }
            for k, v in defaults.items():
                thresholds.setdefault(k, v)
            con.execute(
                """UPDATE channels SET editorial_thresholds_json=?,updated_at=? WHERE id=?""",
                (json.dumps(thresholds, ensure_ascii=False, separators=(",", ":")), now_iso(), int(row["id"])),
            )
            con.execute(
                """UPDATE channel_policies SET selection_rules=?,rejection_rules=?,selector_extra_prompt=?,writer_extra_prompt=?,updated_at=? WHERE channel_id=?""",
                (
                    add_once(row["selection_rules"], selection_block),
                    add_once(row["rejection_rules"], rejection_block),
                    add_once(row["selector_extra_prompt"], selector_block),
                    add_once(row["writer_extra_prompt"], writer_block),
                    now_iso(), int(row["id"]),
                ),
            )
        con.execute(
            "INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, "1"),
        )

    @staticmethod
    def _ensure_rc71_commercial_media_quality_policy(con: sqlite3.Connection) -> None:
        """Require trustworthy media for explicitly commercial-editorial channels.

        This remains ordinary visible per-channel policy data.  The runtime contains no
        channel name/ID rule; existing channels explicitly configured with the
        commercial_editorial profile receive the one-time seed and users can edit it.
        """
        key = "rc71_commercial_media_quality_policy_v1"
        done = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        if done and str(done[0] or "") == "1":
            return
        rows = con.execute(
            "SELECT id FROM channels WHERE editorial_runtime_profile=?",
            (str(EditorialRuntimeProfile.COMMERCIAL_EDITORIAL),),
        ).fetchall()
        stamp = now_iso()
        for row in rows:
            con.execute(
                "UPDATE channel_policies SET media_policy='required',updated_at=? WHERE channel_id=?",
                (stamp, int(row["id"])),
            )
        con.execute(
            "INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, "1"),
        )

    @staticmethod
    def _ensure_rc72_channel_policy_tuning(con: sqlite3.Connection) -> None:
        """One-time visible policy tuning for explicit persisted channel roles.

        No channel names or IDs are used. Commercial-editorial channels get a
        broad-audience-first mix while preserving required media. Monitoring
        channels keep their existing policy; VIDEO_PENDING retry cadence is
        derived at runtime from their visible poll interval.
        """
        key = "rc72_channel_policy_tuning_v1"
        done = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        if done and str(done[0] or "") == "1":
            return

        rows = con.execute(
            """SELECT c.id,c.editorial_thresholds_json,p.selection_rules,p.rejection_rules,p.selector_extra_prompt,p.writer_extra_prompt
                 FROM channels c JOIN channel_policies p ON p.channel_id=c.id
                WHERE c.editorial_runtime_profile=?""",
            (str(EditorialRuntimeProfile.COMMERCIAL_EDITORIAL),),
        ).fetchall()
        selection_block = (
            "[BROAD_AUDIENCE_RC72]\n"
            "Редакційний пріоритет каналу: приблизно 70–80% матеріалів мають бути цікавими широкій аудиторії, "
            "а не лише професійним маркетологам. Перевага: дивні товари/ціни, бренди у попкультурі, меми, viral, "
            "споживчі звички, технології у повсякденному житті, культурні конфлікти, незвичні колаборації, факапи, "
            "провокації та історії, які хочеться переказати. Профільний case study — максимум другорядний формат і "
            "має проходити лише коли сюжет цікавий поза професією."
        )
        rejection_block = (
            "[BROAD_AUDIENCE_RC72]\n"
            "Жорсткіше відхиляй рутинні agency/B2B кейси, award recap, KPI-only campaign reports, retail/marketing trade news "
            "і 'бренд зробив кампанію' без людського сюжету, сюрпризу або широкого consumer/culture relevance."
        )
        selector_block = (
            "[BROAD_AUDIENCE_RC72] Broad-audience lane is the DEFAULT preference. A professional commercial case should lose "
            "to a weaker-but-interesting general-audience story unless the case has a genuinely unusual human/cultural/consumer hook. "
            "Do not reward trade jargon, campaign mechanics or measurable uplift by themselves."
        )
        writer_block = (
            "[BROAD_AUDIENCE_RC72] Подавай як цікаву історію для людини поза професією. Не перетворюй текст на case-study summary, "
            "не додавай 'уроки для маркетологів' і не починай з професійної механіки, якщо є сильніший людський факт."
        )

        def add_once(value: str, block: str) -> str:
            base = str(value or "").strip()
            if "[BROAD_AUDIENCE_RC72]" in base:
                return base
            return (base + "\n\n" + block).strip() if base else block

        stamp = now_iso()
        for row in rows:
            try:
                thresholds = json.loads(str(row["editorial_thresholds_json"] or "{}"))
            except Exception:
                thresholds = {}
            if not isinstance(thresholds, dict):
                thresholds = {}
            # Make broad-interest easier than professional case lanes; keep every
            # value in the ordinary channel JSON so the operator can edit it.
            thresholds.update({
                "broad_interest_fit": 48,
                "broad_interest_score": 44,
                "broad_general_interest": 50,
                "broad_retellability": 50,
                "broad_culture_or_surprise": 45,
                "commercial_case_score": 60,
                "commercial_transferability": 55,
                "commercial_anchor": 65,
                "creative_case_score": 56,
                "mechanism_case_score": 55,
            })
            con.execute(
                "UPDATE channels SET editorial_thresholds_json=?,updated_at=? WHERE id=?",
                (json.dumps(thresholds, ensure_ascii=False, separators=(",", ":")), stamp, int(row["id"])),
            )
            con.execute(
                """UPDATE channel_policies SET selection_rules=?,rejection_rules=?,selector_extra_prompt=?,writer_extra_prompt=?,
                           media_policy='required',updated_at=? WHERE channel_id=?""",
                (
                    add_once(row["selection_rules"], selection_block),
                    add_once(row["rejection_rules"], rejection_block),
                    add_once(row["selector_extra_prompt"], selector_block),
                    add_once(row["writer_extra_prompt"], writer_block),
                    stamp, int(row["id"]),
                ),
            )

        con.execute(
            "INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, "1"),
        )

    def run_startup_maintenance(self) -> dict[str, int]:
        """Run potentially expensive one-time maintenance outside the Tk/UI thread.

        RC8 executed URL backfill synchronously from ``V2Store.__init__`` before the main
        window existed. On a migrated database that could look exactly like an application
        hang. RC9 keeps schema creation synchronous (fast) and exposes maintenance explicitly
        so the launcher can run it in a background worker before starting the runtime.
        """
        normalized = self._normalize_existing_canonical_urls()
        reconciled = self._reconcile_published_url_duplicates()
        recovered_hotlinks = self._recover_rc17_hotlink_failures()
        sanitized_telegram = self._sanitize_pre_rc18_telegram_media()
        return {
            "normalized_urls": int(normalized),
            "reconciled_duplicates": int(reconciled),
            "recovered_hotlink_failures": int(recovered_hotlinks),
            "sanitized_telegram_media": int(sanitized_telegram),
        }

    def _sanitize_pre_rc18_telegram_media(self) -> int:
        """Remove contaminated Telegram media snapshots produced before RC18.

        RC17 could store the channel avatar and video poster as attachments. Those
        URLs cannot be reliably distinguished later without their HTML ancestry, so
        pending Telegram rows using the old filter version are reset and allowed to
        be repopulated by the next clean t.me/s ingest. Published history is never
        modified.
        """
        key = "rc18_telegram_media_filter_reset_v1"
        with self.connect() as con:
            done = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
            if done and str(done[0] or "") == "1":
                return 0
        changed = 0
        stamp = now_iso()
        with self.transaction() as con:
            try:
                con.execute("BEGIN IMMEDIATE")
                rows = con.execute("SELECT id,article_layout_json FROM articles WHERE stage<>'PUBLISHED' AND decision='PENDING'").fetchall()
                for row in rows:
                    try:
                        layout=json.loads(str(row["article_layout_json"] or "{}"))
                    except Exception:
                        layout={}
                    if not isinstance(layout, dict) or str(layout.get("source_kind") or "").casefold() != "telegram":
                        continue
                    tg=layout.get("telegram")
                    if isinstance(tg, dict) and int(tg.get("media_filter_version") or 0) >= 2:
                        continue
                    # Preserve non-media metadata but make it explicit that this row
                    # needs a clean source snapshot before REQUIRED media can publish.
                    if isinstance(tg, dict):
                        tg["media_count"] = 0
                        tg["media_group"] = False
                        tg["media_filter_version"] = 0
                    layout["blocks"] = [b for b in list(layout.get("blocks") or []) if not (isinstance(b, dict) and str(b.get("type") or "") == "media")]
                    con.execute(
                        "UPDATE articles SET media_json='[]',article_layout_json=?,blocked_by=CASE WHEN blocked_by='MEDIA' THEN blocked_by ELSE blocked_by END,last_error_code=CASE WHEN last_error_code LIKE 'MEDIA_%' THEN last_error_code ELSE last_error_code END WHERE id=?",
                        (json.dumps(layout,ensure_ascii=False,separators=(",", ":")), int(row["id"])),
                    )
                    # Do not force a publish retry with stale fake media. The collector
                    # will refresh recent rows; old rows will age out via max_age_hours.
                    con.execute("UPDATE jobs SET available_at=?,updated_at=? WHERE article_id=? AND state='QUEUED'", (stamp,stamp,int(row["id"])))
                    changed += 1
                con.execute("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, "1"))
                con.commit()
            except Exception:
                con.rollback(); raise
        return changed

    def _recover_rc17_hotlink_failures(self) -> int:
        """Wake READY rows poisoned by RC16 Telegram remote-fetch failures.

        RC17 no longer gives Telegram remote media URLs, so WEBPAGE_CURL_FAILED is
        not a valid reason to keep those articles blocked.  This one-time repair is
        deliberately narrow and never reopens unrelated Telegram/media failures.
        """
        key = "rc17_hotlink_media_recovery_v1"
        with self.connect() as con:
            done = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
            if done and str(done[0] or "") == "1":
                return 0
        stamp = now_iso()
        with self.transaction() as con:
            try:
                con.execute("BEGIN IMMEDIATE")
                cur = con.execute(
                    """UPDATE articles
                       SET blocked_by='NONE',last_error_code='',last_error_detail='',next_retry_at=''
                       WHERE stage='READY' AND decision='PUBLISH'
                         AND blocked_by IN ('TELEGRAM','MEDIA')
                         AND last_error_detail LIKE '%WEBPAGE_CURL_FAILED%'"""
                )
                changed = int(cur.rowcount or 0)
                con.execute(
                    "INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, "1"),
                )
                con.commit()
            except Exception:
                con.rollback(); raise
        return changed

    def _normalize_existing_canonical_urls(self) -> int:
        """One-time RC8 backfill so old tracking URLs participate in exact dedupe."""
        key = "canonical_url_normalization_v1"
        with self.connect() as con:
            done = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
            if done and str(done[0] or "") == "1":
                return 0
        changed = 0
        with self.transaction() as con:
            try:
                con.execute("BEGIN IMMEDIATE")
                rows = con.execute("SELECT id,source_url,canonical_source_url FROM articles").fetchall()
                for row in rows:
                    original = str(row["canonical_source_url"] or row["source_url"] or "").strip()
                    normalized = normalize_url(original)
                    if normalized and normalized != str(row["canonical_source_url"] or ""):
                        con.execute("UPDATE articles SET canonical_source_url=? WHERE id=?", (normalized, int(row["id"])))
                        changed += 1
                con.execute("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, "1"))
                con.commit()
            except Exception:
                con.rollback(); raise
        return changed

    def _reconcile_published_url_duplicates(self) -> int:
        """One-time cleanup: queued/READY copies of an already published normalized URL become DUPLICATE.

        We intentionally do not rewrite two rows that are both already PUBLISHED: RC8 cannot undo
        Telegram history. It only guarantees that another queued copy of that page will not publish again.
        """
        key = "published_url_reconcile_v1"
        with self.connect() as con:
            done = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
            if done and str(done[0] or "") == "1":
                return 0
        changed = 0
        stamp = now_iso()
        with self.transaction() as con:
            try:
                con.execute("BEGIN IMMEDIATE")
                published = con.execute("""SELECT channel_id,canonical_source_url,MAX(id) AS published_id
                    FROM articles WHERE stage='PUBLISHED' AND canonical_source_url<>''
                    GROUP BY channel_id,canonical_source_url""").fetchall()
                for row in published:
                    pid = int(row["published_id"] or 0)
                    if pid <= 0:
                        continue
                    dupes = con.execute("""SELECT id FROM articles WHERE channel_id=? AND canonical_source_url=? AND id<>?
                        AND stage<>'PUBLISHED' AND decision<>'DUPLICATE'""",
                        (int(row["channel_id"]), str(row["canonical_source_url"]), pid)).fetchall()
                    for dup in dupes:
                        aid = int(dup["id"]); detail = f"Already published normalized URL as article #{pid}"
                        con.execute("""UPDATE articles SET stage=?,decision=?,blocked_by=?,duplicate_of=?,reject_reason=?,status_detail=?,last_error_code='',last_error_detail='',next_retry_at='' WHERE id=?""",
                            (str(Stage.DEDUPED), str(Decision.DUPLICATE), str(BlockedBy.NONE), pid, detail, detail, aid))
                        con.execute("UPDATE jobs SET state='DONE',lease_owner='',lease_until='',error_code='',error_detail='',updated_at=? WHERE article_id=? AND state<>'DONE'", (stamp, aid))
                        changed += 1
                con.execute("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, "1"))
                con.commit()
            except Exception:
                con.rollback(); raise
        return changed

    def list_channels(self, *, enabled_only: bool=False) -> list[sqlite3.Row]:
        where=" WHERE enabled=1" if enabled_only else ""
        with self.connect() as con: return list(con.execute(f"SELECT * FROM channels{where} ORDER BY id"))

    def get_channel(self, channel_id: int) -> ChannelConfig | None:
        with self.connect() as con:
            row=con.execute("SELECT * FROM channels WHERE id=?",(int(channel_id),)).fetchone()
            if not row: return None
            p=con.execute("SELECT * FROM channel_policies WHERE channel_id=?",(int(channel_id),)).fetchone()
        policy=ChannelPolicy(
            channel_id=int(row["id"]),enabled=_bool(_row_get(p,"enabled",1),True),purpose=str(_row_get(p,"purpose","") or ""),audience=str(_row_get(p,"audience","") or ""),
            selection_rules=str(_row_get(p,"selection_rules","") or ""),rejection_rules=str(_row_get(p,"rejection_rules","") or ""),writing_rules=str(_row_get(p,"writing_rules","") or ""),
            style_rules=str(_row_get(p,"style_rules","") or ""),positive_examples=str(_row_get(p,"positive_examples","") or ""),negative_examples=str(_row_get(p,"negative_examples","") or ""),
            extra_instructions=str(_row_get(p,"extra_instructions","") or ""),selector_extra_prompt=str(_row_get(p,"selector_extra_prompt","") or ""),writer_extra_prompt=str(_row_get(p,"writer_extra_prompt","") or ""),
            source_body_attribution_mode=SourceBodyAttributionMode(str(_row_get(p,"source_body_attribution_mode","footer_only") or "footer_only")),source_body_attribution_marker=str(_row_get(p,"source_body_attribution_marker","") or ""),
            media_policy=str(_row_get(p,"media_policy","required") or "required"),target_min_chars=int(_row_get(p,"target_min_chars",300) or 300),target_max_chars=int(_row_get(p,"target_max_chars",750) or 750),
        )
        mode=ChannelMode.MONITORING if str(row["channel_mode"]).casefold()=="monitoring" else ChannelMode.EDITORIAL
        try:
            source_attribution_mode=SourceAttributionMode(str(_row_get(row,"source_attribution_mode","standard") or "standard"))
        except Exception:
            source_attribution_mode=SourceAttributionMode.STANDARD
        try:
            dedupe_profile=DedupeProfile(str(_row_get(row,"dedupe_profile","standard") or "standard"))
        except Exception:
            dedupe_profile=DedupeProfile.STANDARD
        try:
            editorial_runtime_profile=EditorialRuntimeProfile(str(_row_get(row,"editorial_runtime_profile","standard") or "standard"))
        except Exception:
            editorial_runtime_profile=EditorialRuntimeProfile.STANDARD
        try:
            raw_facebook_page_ids = json.loads(str(_row_get(row,"facebook_page_ids_json","[]") or "[]"))
        except Exception:
            raw_facebook_page_ids = []
        facebook_page_ids = [str(x).strip() for x in raw_facebook_page_ids if str(x).strip()] if isinstance(raw_facebook_page_ids, list) else []
        return ChannelConfig(
            id=int(row["id"]),name=str(row["name"]),telegram_chat_id=str(row["telegram_chat_id"] or ""),enabled=_bool(row["enabled"],True),mode=mode,
            editorial_profile=str(row["editorial_profile"] or ""),editorial_runtime_profile=editorial_runtime_profile,include_source_link=_bool(row["include_source_link"],True),source_link_required=_bool(row["source_link_required"],True),
            source_attribution_mode=source_attribution_mode,
            poll_interval_minutes=int(row["poll_interval_minutes"] or 5),poll_immediate=_bool(row["poll_immediate"],False),min_publish_interval_minutes=int(row["min_publish_interval_minutes"] or 10),
            dedupe_window_hours=int(row["dedupe_window_hours"] or 72),dedupe_profile=dedupe_profile,
            dedupe_scientific_names=_bool(_row_get(row,"dedupe_scientific_names",0),False),
            dedupe_compound_events=_bool(_row_get(row,"dedupe_compound_events",0),False),
            dedupe_rare_terms=_bool(_row_get(row,"dedupe_rare_terms",0),False),
            published_dedupe_window_hours=int(_row_get(row,"published_dedupe_window_hours",168) or 168),
            max_age_hours=int(row["max_age_hours"] or 24),max_posts_per_cycle=int(row["max_posts_per_cycle"] or 3),
            publish_24h=_bool(row["publish_24h"],False),publish_start=str(row["publish_start"] or "07:00"),publish_end=str(row["publish_end"] or "00:00"),publish_immediately=_bool(row["publish_immediately"],False),
            topic_balance_enabled=_bool(row["topic_balance_enabled"],True),topic_daily_limit=int(row["topic_daily_limit"] or 2),related_spacing_posts=int(row["related_spacing_posts"] or 5),
            editorial_weights_json=str(row["editorial_weights_json"] or "[]"),
            editorial_thresholds_json=str(_row_get(row,"editorial_thresholds_json","{}") or "{}"),
            output_starvation_enabled=_bool(_row_get(row,"output_starvation_enabled",1),True),
            output_starvation_window_hours=max(1,int(_row_get(row,"output_starvation_window_hours",4) or 4)),
            output_starvation_min_processed=max(1,int(_row_get(row,"output_starvation_min_processed",20) or 20)),
            output_starvation_min_published=max(0,int(_row_get(row,"output_starvation_min_published",1) or 0)),
            page_prefer_feed=_bool(_row_get(row,"page_prefer_feed",0),False),
            page_candidate_scan_limit=max(8,min(120,int(_row_get(row,"page_candidate_scan_limit",24) or 24))),
            page_fetch_limit=max(4,min(40,int(_row_get(row,"page_fetch_limit",8) or 8))),
            input_starvation_enabled=_bool(_row_get(row,"input_starvation_enabled",1),True),
            input_starvation_min_seen=max(1,int(_row_get(row,"input_starvation_min_seen",40) or 40)),
            input_starvation_cycles=max(1,int(_row_get(row,"input_starvation_cycles",3) or 3)),
            language_mode=str(row["language_mode"] or "ukru_to_uk"),media_enrichment_mode=str(row["media_enrichment_mode"] or "auto"),
            media_first_allowed=_bool(row["media_first_allowed"],True),media_min_text_chars=int(row["media_min_text_chars"] or 500),
            facebook_page_ids=facebook_page_ids,policy=policy,
        )

    def save_channel(self, cfg: ChannelConfig) -> None:
        stamp=now_iso()
        with self.transaction() as con:
            try:
                con.execute("BEGIN IMMEDIATE")
                con.execute("""UPDATE channels SET name=?,telegram_chat_id=?,enabled=?,channel_mode=?,editorial_profile=?,editorial_runtime_profile=?,include_source_link=?,source_link_required=?,source_attribution_mode=?,poll_interval_minutes=?,poll_immediate=?,min_publish_interval_minutes=?,dedupe_window_hours=?,dedupe_profile=?,dedupe_scientific_names=?,dedupe_compound_events=?,dedupe_rare_terms=?,published_dedupe_window_hours=?,max_age_hours=?,max_posts_per_cycle=?,publish_24h=?,publish_start=?,publish_end=?,publish_immediately=?,topic_balance_enabled=?,topic_daily_limit=?,related_spacing_posts=?,editorial_weights_json=?,editorial_thresholds_json=?,output_starvation_enabled=?,output_starvation_window_hours=?,output_starvation_min_processed=?,output_starvation_min_published=?,page_prefer_feed=?,page_candidate_scan_limit=?,page_fetch_limit=?,input_starvation_enabled=?,input_starvation_min_seen=?,input_starvation_cycles=?,language_mode=?,media_enrichment_mode=?,media_first_allowed=?,media_min_text_chars=?,facebook_page_ids_json=?,updated_at=? WHERE id=?""",
                    (cfg.name,cfg.telegram_chat_id,int(cfg.enabled),str(cfg.mode),cfg.editorial_profile,str(cfg.editorial_runtime_profile),int(cfg.include_source_link),int(cfg.source_link_required),str(cfg.source_attribution_mode),int(cfg.poll_interval_minutes),int(cfg.poll_immediate),int(cfg.min_publish_interval_minutes),int(cfg.dedupe_window_hours),str(cfg.dedupe_profile),int(cfg.dedupe_scientific_names),int(cfg.dedupe_compound_events),int(cfg.dedupe_rare_terms),int(cfg.published_dedupe_window_hours),int(cfg.max_age_hours),int(cfg.max_posts_per_cycle),int(cfg.publish_24h),cfg.publish_start,cfg.publish_end,int(cfg.publish_immediately),int(cfg.topic_balance_enabled),int(cfg.topic_daily_limit),int(cfg.related_spacing_posts),cfg.editorial_weights_json,cfg.editorial_thresholds_json,int(cfg.output_starvation_enabled),int(cfg.output_starvation_window_hours),int(cfg.output_starvation_min_processed),int(cfg.output_starvation_min_published),int(cfg.page_prefer_feed),int(cfg.page_candidate_scan_limit),int(cfg.page_fetch_limit),int(cfg.input_starvation_enabled),int(cfg.input_starvation_min_seen),int(cfg.input_starvation_cycles),cfg.language_mode,cfg.media_enrichment_mode,int(cfg.media_first_allowed),int(cfg.media_min_text_chars),json.dumps(list(dict.fromkeys(str(x).strip() for x in (cfg.facebook_page_ids or []) if str(x).strip())),ensure_ascii=False,separators=(",",":")),stamp,int(cfg.id)))
                p=cfg.policy
                con.execute("""INSERT INTO channel_policies(channel_id,enabled,purpose,audience,selection_rules,rejection_rules,writing_rules,style_rules,positive_examples,negative_examples,extra_instructions,selector_extra_prompt,writer_extra_prompt,source_body_attribution_mode,source_body_attribution_marker,media_policy,target_min_chars,target_max_chars,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(channel_id) DO UPDATE SET enabled=excluded.enabled,purpose=excluded.purpose,audience=excluded.audience,selection_rules=excluded.selection_rules,rejection_rules=excluded.rejection_rules,writing_rules=excluded.writing_rules,style_rules=excluded.style_rules,positive_examples=excluded.positive_examples,negative_examples=excluded.negative_examples,extra_instructions=excluded.extra_instructions,selector_extra_prompt=excluded.selector_extra_prompt,writer_extra_prompt=excluded.writer_extra_prompt,source_body_attribution_mode=excluded.source_body_attribution_mode,source_body_attribution_marker=excluded.source_body_attribution_marker,media_policy=excluded.media_policy,target_min_chars=excluded.target_min_chars,target_max_chars=excluded.target_max_chars,updated_at=excluded.updated_at""",
                    (cfg.id,int(p.enabled),p.purpose,p.audience,p.selection_rules,p.rejection_rules,p.writing_rules,p.style_rules,p.positive_examples,p.negative_examples,p.extra_instructions,p.selector_extra_prompt,p.writer_extra_prompt,str(p.source_body_attribution_mode),p.source_body_attribution_marker,p.media_policy,int(p.target_min_chars),int(p.target_max_chars),stamp))
                con.commit()
            except Exception: con.rollback(); raise

    def queue_facebook_reposts(
        self, article_id: int, channel_id: int, page_ids: list[str] | tuple[str, ...],
        *, telegram_message_id: str, telegram_post_url: str,
    ) -> int:
        page_ids = list(dict.fromkeys(str(x).strip() for x in page_ids if str(x).strip()))
        if not page_ids or not str(telegram_post_url or "").strip():
            return 0
        stamp = now_iso()
        with self.transaction() as con:
            try:
                con.execute("BEGIN IMMEDIATE")
                for page_id in page_ids:
                    con.execute(
                        """INSERT INTO facebook_reposts(article_id,channel_id,page_id,telegram_message_id,telegram_post_url,state,attempts,next_retry_at,facebook_post_id,last_error,created_at,updated_at)
                           VALUES(?,?,?,?,?,'PENDING',0,'','','',?,?)
                           ON CONFLICT(article_id,page_id) DO UPDATE SET
                             telegram_message_id=excluded.telegram_message_id,telegram_post_url=excluded.telegram_post_url,
                             state=CASE WHEN facebook_reposts.facebook_post_id<>'' THEN 'DONE' ELSE facebook_reposts.state END,
                             updated_at=excluded.updated_at""",
                        (int(article_id),int(channel_id),page_id,str(telegram_message_id or ""),str(telegram_post_url or ""),stamp,stamp),
                    )
                con.commit()
            except Exception:
                con.rollback(); raise
        return len(page_ids)

    def pending_facebook_reposts(self, channel_id: int, *, limit: int = 12) -> list[sqlite3.Row]:
        with self.connect() as con:
            return list(con.execute(
                """SELECT r.*,a.final_text,a.title,a.published_at,c.name AS channel_name,c.telegram_chat_id
                   FROM facebook_reposts r
                   JOIN articles a ON a.id=r.article_id
                   JOIN channels c ON c.id=r.channel_id
                   WHERE r.channel_id=? AND r.state<>'DONE'
                     AND (r.next_retry_at='' OR datetime(r.next_retry_at)<=datetime('now'))
                   ORDER BY r.updated_at ASC LIMIT ?""",
                (int(channel_id),max(1,int(limit))),
            ))

    def mark_facebook_repost_done(self, article_id: int, page_id: str, facebook_post_id: str) -> None:
        with self.connect() as con:
            con.execute(
                "UPDATE facebook_reposts SET state='DONE',facebook_post_id=?,last_error='',next_retry_at='',updated_at=? WHERE article_id=? AND page_id=?",
                (str(facebook_post_id or ""),now_iso(),int(article_id),str(page_id)),
            )

    def mark_facebook_repost_failed(self, article_id: int, page_id: str, error_text: str, *, retryable: bool = True) -> str:
        with self.connect() as con:
            row=con.execute("SELECT attempts FROM facebook_reposts WHERE article_id=? AND page_id=?",(int(article_id),str(page_id))).fetchone()
            attempts=int(row[0] or 0)+1 if row else 1
            if retryable:
                minutes=min(360, max(5, 5 * (2 ** min(6, attempts - 1))))
                next_retry=(datetime.now(timezone.utc)+timedelta(minutes=minutes)).isoformat(timespec="seconds")
                state='RETRY'
            else:
                next_retry=(datetime.now(timezone.utc)+timedelta(hours=6)).isoformat(timespec="seconds")
                state='BLOCKED'
            con.execute(
                "UPDATE facebook_reposts SET state=?,attempts=?,next_retry_at=?,last_error=?,updated_at=? WHERE article_id=? AND page_id=?",
                (state,attempts,next_retry,str(error_text or "")[:1600],now_iso(),int(article_id),str(page_id)),
            )
        return next_retry

    def facebook_repost_rows(self, article_id: int) -> list[sqlite3.Row]:
        with self.connect() as con:
            return list(con.execute("SELECT * FROM facebook_reposts WHERE article_id=? ORDER BY page_id",(int(article_id),)))

    def sources_for_channel(self, channel_id: int, *, enabled_only: bool=True) -> list[sqlite3.Row]:
        clause=" AND enabled=1" if enabled_only else ""
        with self.connect() as con: return list(con.execute(f"SELECT * FROM sources WHERE channel_id=?{clause} ORDER BY priority,id",(int(channel_id),)))

    def get_article(self, article_id: int) -> sqlite3.Row | None:
        with self.connect() as con: return con.execute("SELECT a.*,s.name AS source_name,s.url AS source_root_url FROM articles a JOIN sources s ON s.id=a.source_id WHERE a.id=?",(int(article_id),)).fetchone()

    def find_equivalent_article(self, channel_id: int, url: str, *, exclude_article_id: int | None = None, published_only: bool = False, hours: int | None = None) -> sqlite3.Row | None:
        target = normalize_url(url)
        if not target:
            return None
        clauses = ["channel_id=?", "canonical_source_url=?"]
        args: list[Any] = [int(channel_id), target]
        if exclude_article_id is not None:
            clauses.append("id<>?"); args.append(int(exclude_article_id))
        if published_only:
            clauses.append("stage='PUBLISHED'")
        if hours is not None and int(hours) > 0:
            time_col = "published_at" if published_only else "discovered_at"
            clauses.append(f"datetime({time_col})>=datetime('now',?)")
            args.append(f"-{max(1,int(hours))} hours")
        query = "SELECT * FROM articles WHERE " + " AND ".join(clauses) + " ORDER BY id DESC LIMIT 1"
        with self.connect() as con:
            row = con.execute(query, tuple(args)).fetchone()
            if row is not None:
                return row
            # Compatibility fallback for databases that have not yet been backfilled or
            # imported rows carrying a raw tracking URL. Keep this bounded.
            scan_clauses = ["channel_id=?"]
            scan_args: list[Any] = [int(channel_id)]
            if exclude_article_id is not None:
                scan_clauses.append("id<>?"); scan_args.append(int(exclude_article_id))
            if published_only:
                scan_clauses.append("stage='PUBLISHED'")
            if hours is not None and int(hours) > 0:
                time_col = "published_at" if published_only else "discovered_at"
                scan_clauses.append(f"datetime({time_col})>=datetime('now',?)")
                scan_args.append(f"-{max(1,int(hours))} hours")
            scan = con.execute("SELECT * FROM articles WHERE " + " AND ".join(scan_clauses) + " ORDER BY id DESC LIMIT 2000", tuple(scan_args)).fetchall()
            for candidate in scan:
                value = str(candidate["canonical_source_url"] or candidate["source_url"] or "")
                if normalize_url(value) == target:
                    return candidate
        return None

    def recent_candidates(self, channel_id: int, *, article_id: int, hours: int=72, limit: int=120) -> list[sqlite3.Row]:
        with self.connect() as con:
            return list(con.execute("""SELECT a.*,s.name AS source_name FROM articles a JOIN sources s ON s.id=a.source_id WHERE a.channel_id=? AND a.id<>? AND datetime(a.discovered_at)>=datetime('now',?) AND a.stage<>'ARCHIVED' ORDER BY a.id DESC LIMIT ?""",(int(channel_id),int(article_id),f"-{max(1,int(hours))} hours",max(1,int(limit)))))

    def last_published_at(self, channel_id: int) -> str:
        with self.connect() as con:
            row=con.execute("SELECT published_at FROM articles WHERE channel_id=? AND stage='PUBLISHED' AND published_at<>'' ORDER BY datetime(published_at) DESC,id DESC LIMIT 1",(int(channel_id),)).fetchone()
            return str(row[0] or "") if row else ""

    def ready_articles(self, channel_id: int, limit: int=100) -> list[sqlite3.Row]:
        """Return publishable READY rows without retry-storming blocked articles.

        A READY article blocked by Telegram/media is eligible again only when an
        explicit ``next_retry_at`` has elapsed.  Permanent/media-refresh blockers
        with an empty retry timestamp stay quiet until ingest or operator action
        clears the blocker.
        """
        stamp = now_iso()
        with self.connect() as con:
            return list(con.execute(
                """SELECT a.*,s.name AS source_name
                   FROM articles a JOIN sources s ON s.id=a.source_id
                   WHERE a.channel_id=? AND a.stage='READY' AND a.decision='PUBLISH'
                     AND (a.blocked_by='NONE' OR (a.next_retry_at<>'' AND datetime(a.next_retry_at)<=datetime(?)))
                   ORDER BY datetime(CASE WHEN a.source_published_at<>'' THEN a.source_published_at ELSE a.discovered_at END) DESC,a.id DESC
                   LIMIT ?""",
                (int(channel_id), stamp, max(1,int(limit))),
            ))

    def publication_backoff(
        self,
        article_id: int,
        *,
        blocked_by: BlockedBy,
        error_code: str,
        detail: str,
        retry_seconds: int | None,
        count_attempt: bool = True,
    ) -> str:
        """Persist publication failure backoff directly on the article.

        Publication itself is not a separate job, so relying on the processing-job
        lease cannot throttle retries.  RC16 therefore retried definite Telegram
        4xx failures several times per second.  RC17 gives READY publication its
        own durable clock. ``None`` means wait for source/operator refresh.
        """
        retry_at = ''
        if retry_seconds is not None:
            retry_at = (datetime.now(timezone.utc) + timedelta(seconds=max(30, int(retry_seconds)))).astimezone().isoformat(timespec='seconds')
        with self.connect() as con:
            con.execute(
                """UPDATE articles SET blocked_by=?,last_error_code=?,last_error_detail=?,next_retry_at=?,
                          retry_count=retry_count+? WHERE id=?""",
                (str(blocked_by), str(error_code)[:120], str(detail)[:2000], retry_at, 1 if count_attempt else 0, int(article_id)),
            )
        return retry_at

    def update_article(self, article_id: int, **fields: Any) -> None:
        allowed={"title","source_url","canonical_source_url","raw_text","content_hash","source_published_at","stage","decision","blocked_by","status_detail","reject_reason","duplicate_of","event_key","event_summary","editorial_category","editorial_value_score","tags_json","topic_major","topic_minor","draft_text","final_text","ai_provider","ai_model","media_json","article_layout_json","ready_at","published_at","telegram_message_id","telegram_media_count","last_error_code","last_error_detail","retry_count","next_retry_at","legacy_status"}
        clean={k:v for k,v in fields.items() if k in allowed}
        if not clean: return
        assignments=",".join(f"{k}=?" for k in clean)
        with self.connect() as con: con.execute(f"UPDATE articles SET {assignments} WHERE id=?",tuple(clean.values())+(int(article_id),))

    def insert_collected(self, *, channel_id:int,source_id:int,external_id:str,title:str,source_url:str,raw_text:str,content_hash:str="",source_published_at:str="",media_json:str="[]",article_layout_json:str="{}") -> int:
        stamp=now_iso(); canonical=normalize_url(str(source_url or "").strip())
        source_published_at = _normalize_datetime_value(str(source_published_at or ""))
        is_telegram_snapshot = _layout_source_kind(article_layout_json) == "telegram"
        with self.transaction() as con:
            try:
                con.execute("BEGIN IMMEDIATE")
                row=con.execute("SELECT id,stage,decision,media_json,article_layout_json,last_error_code FROM articles WHERE channel_id=? AND source_id=? AND external_id=?",(int(channel_id),int(source_id),str(external_id))).fetchone()
                if row:
                    aid = int(row["id"])
                    # Telegram/web pages can reveal the media part one poll later than
                    # the text. Refresh non-published rows instead of freezing the first
                    # incomplete snapshot forever.
                    if str(row["stage"]) != str(Stage.PUBLISHED):
                        refreshed_media = _clean_media_json(str(media_json or "[]")) if is_telegram_snapshot else _merge_media_json(str(row["media_json"] or "[]"), str(media_json or "[]"))
                        refreshed_layout = _refresh_layout(str(row["article_layout_json"] or "{}"), str(article_layout_json or "{}"))
                        media_ready = _media_json_count(refreshed_media) > 0
                        clean_telegram_snapshot = is_telegram_snapshot and _telegram_media_filter_version(refreshed_layout) >= 2
                        prior_error = str(row["last_error_code"] or "")
                        refreshed_video_ok = _telegram_video_recovery(refreshed_layout) in {"direct_video", "exact_post_video"} and _media_json_has_video(refreshed_media)
                        clear_media_block = (
                            (prior_error == "TELEGRAM_MEDIA_REFRESH_REQUIRED" and clean_telegram_snapshot)
                            or (prior_error == "TELEGRAM_VIDEO_PENDING" and refreshed_video_ok)
                            or (prior_error in {"MEDIA_REQUIRED","MEDIA_MISSING_AFTER_INGEST","MEDIA_DOWNLOAD_FAILED","VIDEO_SOURCE_UNAVAILABLE"} and media_ready)
                        )
                        clear_flag = 1 if clear_media_block else 0
                        con.execute(
                            "UPDATE articles SET title=?,source_url=?,canonical_source_url=?,raw_text=?,content_hash=?,source_published_at=?,media_json=?,article_layout_json=?,blocked_by=CASE WHEN blocked_by='MEDIA' AND ?=1 THEN 'NONE' ELSE blocked_by END,last_error_code=CASE WHEN blocked_by='MEDIA' AND ?=1 THEN '' ELSE last_error_code END,last_error_detail=CASE WHEN blocked_by='MEDIA' AND ?=1 THEN '' ELSE last_error_detail END,next_retry_at=CASE WHEN blocked_by='MEDIA' AND ?=1 THEN '' ELSE next_retry_at END WHERE id=?",
                            (str(title),str(source_url),canonical,str(raw_text),str(content_hash),str(source_published_at),refreshed_media,refreshed_layout,clear_flag,clear_flag,clear_flag,clear_flag,aid),
                        )
                        if clear_media_block:
                            con.execute("UPDATE jobs SET state='QUEUED',available_at=?,lease_owner='',lease_until='',error_code='',error_detail='',updated_at=? WHERE article_id=? AND state='WAITING'",(stamp,stamp,aid))
                    con.commit(); return aid
                # Hard identity guard: the same article URL must not become a second DB row
                # merely because the publisher changed utm_/itm_/ref style tracking parameters.
                if canonical:
                    row=con.execute("SELECT id,stage,media_json,article_layout_json FROM articles WHERE channel_id=? AND canonical_source_url=? ORDER BY id DESC LIMIT 1",(int(channel_id),canonical)).fetchone()
                    if row:
                        aid = int(row["id"])
                        if str(row["stage"]) != str(Stage.PUBLISHED):
                            refreshed_media = _clean_media_json(str(media_json or "[]")) if is_telegram_snapshot else _merge_media_json(str(row["media_json"] or "[]"), str(media_json or "[]"))
                            refreshed_layout = _refresh_layout(str(row["article_layout_json"] or "{}"), str(article_layout_json or "{}"))
                            con.execute("UPDATE articles SET media_json=?,article_layout_json=? WHERE id=?",(refreshed_media,refreshed_layout,aid))
                        con.commit(); return aid
                cur=con.execute("INSERT INTO articles(channel_id,source_id,external_id,title,source_url,canonical_source_url,raw_text,content_hash,source_published_at,discovered_at,media_json,article_layout_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(int(channel_id),int(source_id),str(external_id),str(title),str(source_url),canonical,str(raw_text),str(content_hash),str(source_published_at),stamp,str(media_json),str(article_layout_json)))
                aid=int(cur.lastrowid); con.commit()
            except Exception: con.rollback(); raise
        self.enqueue(aid,channel_id=channel_id,priority=10); return aid

    def enqueue(self, article_id:int, *, channel_id:int|None=None,priority:int=100,available_at:str|None=None,job_type:str="process") -> int:
        stamp=now_iso(); available=available_at or stamp
        if channel_id is None:
            row=self.get_article(article_id)
            if row is None: raise KeyError(article_id)
            channel_id=int(row["channel_id"])
        with self.connect() as con:
            con.execute("""INSERT INTO jobs(article_id,channel_id,job_type,state,priority,available_at,created_at,updated_at) VALUES(?,?,?,'QUEUED',?,?,?,?) ON CONFLICT(article_id,job_type) DO UPDATE SET state=CASE WHEN jobs.state='DONE' THEN jobs.state ELSE 'QUEUED' END,priority=MIN(jobs.priority,excluded.priority),available_at=excluded.available_at,lease_owner='',lease_until='',updated_at=excluded.updated_at""",(int(article_id),int(channel_id),str(job_type),int(priority),str(available),stamp,stamp))
            row=con.execute("SELECT id FROM jobs WHERE article_id=? AND job_type=?",(int(article_id),str(job_type))).fetchone(); return int(row["id"])

    def recover_stale_leases(self) -> int:
        with self.connect() as con:
            cur=con.execute("UPDATE jobs SET state='QUEUED',lease_owner='',lease_until='',updated_at=? WHERE state='LEASED' AND lease_until<>'' AND datetime(lease_until)<=datetime('now')",(now_iso(),)); return int(cur.rowcount or 0)

    def claim_job(self, *, channel_id:int|None=None,worker_id:str|None=None,lease_seconds:int=180) -> sqlite3.Row|None:
        owner=worker_id or f"worker-{uuid.uuid4().hex[:10]}"; until=(datetime.now(timezone.utc)+timedelta(seconds=max(30,int(lease_seconds)))).astimezone().isoformat(timespec="seconds"); stamp=now_iso()
        with self.transaction() as con:
            try:
                con.execute("BEGIN IMMEDIATE"); args=[]; channel_sql=""
                if channel_id is not None: channel_sql=" AND j.channel_id=?"; args.append(int(channel_id))
                # Fresh-first remains the default, but jobs within four hours of their
                # channel TTL get a rescue lane so they are processed instead of simply
                # aging out while newer items continually arrive.
                row=con.execute("""SELECT j.* FROM jobs j JOIN articles a ON a.id=j.article_id JOIN channels c ON c.id=j.channel_id
                    WHERE j.state IN ('QUEUED','WAITING') AND datetime(j.available_at)<=datetime('now') AND a.decision='PENDING'"""+channel_sql+"""
                    ORDER BY j.priority ASC,
                      CASE WHEN (julianday('now')-julianday(CASE WHEN a.source_published_at<>'' THEN a.source_published_at ELSE a.discovered_at END))*24.0 >= MAX(1,c.max_age_hours-4) THEN 0 ELSE 1 END ASC,
                      CASE WHEN (julianday('now')-julianday(CASE WHEN a.source_published_at<>'' THEN a.source_published_at ELSE a.discovered_at END))*24.0 >= MAX(1,c.max_age_hours-4) THEN julianday(CASE WHEN a.source_published_at<>'' THEN a.source_published_at ELSE a.discovered_at END) END ASC,
                      CASE WHEN (julianday('now')-julianday(CASE WHEN a.source_published_at<>'' THEN a.source_published_at ELSE a.discovered_at END))*24.0 < MAX(1,c.max_age_hours-4) THEN julianday(CASE WHEN a.source_published_at<>'' THEN a.source_published_at ELSE a.discovered_at END) END DESC,
                      j.id ASC LIMIT 1""",tuple(args)).fetchone()
                if row is None: con.commit(); return None
                con.execute("UPDATE jobs SET state='LEASED',lease_owner=?,lease_until=?,updated_at=? WHERE id=?",(owner,until,stamp,int(row["id"]))); con.commit(); jid=int(row["id"])
            except Exception: con.rollback(); raise
        with self.connect() as read: return read.execute("SELECT * FROM jobs WHERE id=?",(jid,)).fetchone()

    def finish_job(self, job_id:int) -> None:
        with self.connect() as con: con.execute("UPDATE jobs SET state='DONE',lease_owner='',lease_until='',updated_at=? WHERE id=?",(now_iso(),int(job_id)))

    def cancel_job(self, job_id:int, reason:str="") -> None:
        with self.connect() as con: con.execute("UPDATE jobs SET state='CANCELLED',lease_owner='',lease_until='',error_detail=?,updated_at=? WHERE id=?",(str(reason)[:2000],now_iso(),int(job_id)))

    def defer_job(self, job_id:int, *, blocked_by:BlockedBy,error_code:str,detail:str,retry_seconds:int=300,count_attempt:bool=False) -> None:
        available=(datetime.now(timezone.utc)+timedelta(seconds=max(30,int(retry_seconds)))).astimezone().isoformat(timespec="seconds"); stamp=now_iso()
        with self.connect() as con:
            row=con.execute("SELECT article_id FROM jobs WHERE id=?",(int(job_id),)).fetchone()
            if not row:return
            con.execute("UPDATE jobs SET state='WAITING',available_at=?,lease_owner='',lease_until='',attempts=attempts+?,error_code=?,error_detail=?,updated_at=? WHERE id=?",(available,1 if count_attempt else 0,str(error_code)[:120],str(detail)[:2000],stamp,int(job_id)))
            con.execute("UPDATE articles SET blocked_by=?,last_error_code=?,last_error_detail=?,next_retry_at=?,retry_count=retry_count+? WHERE id=?",(str(blocked_by),str(error_code)[:120],str(detail)[:2000],available,1 if count_attempt else 0,int(row["article_id"])))

    def expire_stale_jobs(self, channel_id:int, max_age_hours:int) -> int:
        """Archive pending work older than the channel maximum age.

        RC17 delegated timestamp parsing to SQLite ``datetime()``. Telegram/RSS rows
        can carry RFC2822 dates (for example ``Fri, 11 Sep 2026 13:20:00 +0300``),
        which SQLite does not parse, so stale jobs survived beyond TTL. RC18 parses
        timestamps in Python, normalizes parseable legacy values to ISO, and expires
        the same conservative QUEUED/WAITING + PENDING set.
        """
        hours=int(max_age_hours or 0)
        if hours <= 0:
            return 0
        cutoff=datetime.now(timezone.utc)-timedelta(hours=hours)
        stamp=now_iso(); reason=f"Перевищено максимальний вік матеріалу ({hours} год)."
        with self.transaction() as con:
            try:
                con.execute("BEGIN IMMEDIATE")
                rows=con.execute(
                    """SELECT DISTINCT j.article_id,a.source_published_at,a.discovered_at
                       FROM jobs j JOIN articles a ON a.id=j.article_id
                       WHERE j.channel_id=?
                         AND j.state IN ('QUEUED','WAITING')
                         AND a.decision='PENDING'
                         AND a.stage<>'READY' AND a.stage<>'PUBLISHED'""",
                    (int(channel_id),),
                ).fetchall()
                ids: list[int] = []
                for row in rows:
                    aid=int(row["article_id"])
                    source_raw=str(row["source_published_at"] or "").strip()
                    discovered_raw=str(row["discovered_at"] or "").strip()
                    dt=_parse_datetime_value(source_raw) or _parse_datetime_value(discovered_raw)
                    if source_raw:
                        normalized=_normalize_datetime_value(source_raw)
                        if normalized and normalized != source_raw and _parse_datetime_value(normalized) is not None:
                            con.execute("UPDATE articles SET source_published_at=? WHERE id=?", (normalized, aid))
                    if dt is not None and dt < cutoff:
                        ids.append(aid)
                if not ids:
                    con.commit(); return 0
                ids=list(dict.fromkeys(ids))
                marks=','.join('?' for _ in ids)
                con.execute(
                    f"UPDATE jobs SET state='DONE',lease_owner='',lease_until='',error_code='STALE_MAX_AGE',error_detail=?,updated_at=? WHERE channel_id=? AND article_id IN ({marks}) AND state IN ('QUEUED','WAITING')",
                    (reason,stamp,int(channel_id),*ids),
                )
                con.execute(
                    f"UPDATE articles SET stage=?,decision=?,blocked_by=?,reject_reason=?,last_error_code='STALE_MAX_AGE',last_error_detail=?,next_retry_at='' WHERE id IN ({marks}) AND decision='PENDING'",
                    (str(Stage.ARCHIVED),str(Decision.REJECT),str(BlockedBy.NONE),reason,reason,*ids),
                )
                con.commit(); return len(ids)
            except Exception:
                con.rollback(); raise

    def requeue_quality_rewrite(self, article_id:int, *, error_code:str, detail:str, max_attempts:int=3) -> str:
        stamp=now_iso(); max_attempts=max(1,int(max_attempts))
        with self.transaction() as con:
            try:
                con.execute("BEGIN IMMEDIATE")
                row=con.execute("SELECT channel_id FROM articles WHERE id=?",(int(article_id),)).fetchone()
                if row is None:
                    con.commit(); return "ARTICLE_MISSING"
                retry_job=con.execute("SELECT attempts FROM jobs WHERE article_id=? AND job_type='rewrite_oversize'",(int(article_id),)).fetchone()
                attempt=(int(retry_job["attempts"] or 0) if retry_job else 0)+1
                if attempt>=max_attempts:
                    con.execute("UPDATE articles SET stage=?,decision=?,blocked_by=?,last_error_code=?,last_error_detail=?,retry_count=retry_count+1,next_retry_at='' WHERE id=?",(str(Stage.QA_PASSED),str(Decision.PENDING),str(BlockedBy.QUALITY),"TELEGRAM_OVERSIZE_BLOCKED",str(detail)[:2000],int(article_id)))
                    con.execute("UPDATE jobs SET state='DONE',lease_owner='',lease_until='',attempts=?,error_code=?,error_detail=?,updated_at=? WHERE article_id=? AND job_type='rewrite_oversize'",(attempt,"TELEGRAM_OVERSIZE_BLOCKED",str(detail)[:2000],stamp,int(article_id)))
                    con.commit(); return "QUALITY_BLOCKED"
                con.execute("UPDATE articles SET stage=?,decision=?,blocked_by=?,last_error_code=?,last_error_detail=?,retry_count=retry_count+1,next_retry_at=? WHERE id=?",(str(Stage.QA_PASSED),str(Decision.PENDING),str(BlockedBy.QUALITY),str(error_code)[:120],str(detail)[:2000],stamp,int(article_id)))
                con.execute("""INSERT INTO jobs(article_id,channel_id,job_type,state,priority,available_at,lease_owner,lease_until,attempts,error_code,error_detail,created_at,updated_at)
                               VALUES(?,?,'rewrite_oversize','QUEUED',0,?,'','',1,?,?,?,?)
                               ON CONFLICT(article_id,job_type) DO UPDATE SET state='QUEUED',priority=0,available_at=excluded.available_at,lease_owner='',lease_until='',attempts=jobs.attempts+1,error_code=excluded.error_code,error_detail=excluded.error_detail,updated_at=excluded.updated_at""",(int(article_id),int(row["channel_id"]),stamp,str(error_code)[:120],str(detail)[:2000],stamp,stamp))
                con.commit(); return "QUALITY_REWRITE_QUEUED"
            except Exception:
                con.rollback(); raise

    def block_article(self, article_id:int, *, blocked_by:BlockedBy, error_code:str, detail:str) -> None:
        self.update_article(int(article_id),stage=str(Stage.QA_PASSED),decision=str(Decision.PENDING),blocked_by=str(blocked_by),last_error_code=str(error_code)[:120],last_error_detail=str(detail)[:2000],next_retry_at='')

    def wake_blocked(self, blocked_by:BlockedBy, *, limit:int=20) -> int:
        stamp=now_iso()
        with self.transaction() as con:
            try:
                con.execute("BEGIN IMMEDIATE"); rows=con.execute("""SELECT j.id,j.article_id FROM jobs j JOIN articles a ON a.id=j.article_id WHERE j.state='WAITING' AND a.blocked_by=? AND a.decision='PENDING' ORDER BY CASE WHEN a.source_published_at<>'' THEN datetime(a.source_published_at) ELSE datetime(a.discovered_at) END DESC,j.id ASC LIMIT ?""",(str(blocked_by),max(1,int(limit)))).fetchall()
                for row in rows:
                    con.execute("UPDATE jobs SET state='QUEUED',available_at=?,lease_owner='',lease_until='',error_code='',error_detail='',updated_at=? WHERE id=?",(stamp,stamp,int(row["id"])))
                    con.execute("UPDATE articles SET blocked_by='NONE',last_error_code='',last_error_detail='',next_retry_at='' WHERE id=?",(int(row["article_id"]),))
                con.commit(); return len(rows)
            except Exception: con.rollback(); raise

    def source_health(self, source_id: int) -> sqlite3.Row | None:
        with self.connect() as con:
            return con.execute("SELECT * FROM source_health WHERE source_id=?", (int(source_id),)).fetchone()

    def source_cooldown_active(self, source_id: int) -> tuple[bool, str]:
        row = self.source_health(source_id)
        until = str(_row_get(row, "cooldown_until", "") or "")
        if not until:
            return False, ""
        try:
            dt = datetime.fromisoformat(until.replace("Z", "+00:00"))
            if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc) > datetime.now(timezone.utc), until
        except Exception:
            return False, until

    def record_source_success(self, source_id: int, duration_ms: int) -> None:
        stamp = now_iso()
        with self.connect() as con:
            con.execute("""INSERT INTO source_health(source_id,consecutive_failures,cooldown_until,last_duration_ms,last_outcome,last_error,updated_at)
                           VALUES(?,0,'',?,'OK','',?)
                           ON CONFLICT(source_id) DO UPDATE SET consecutive_failures=0,cooldown_until='',last_duration_ms=excluded.last_duration_ms,last_outcome='OK',last_error='',updated_at=excluded.updated_at""",
                        (int(source_id), max(0,int(duration_ms)), stamp))

    def record_source_failure(self, source_id: int, duration_ms: int, detail: str) -> tuple[int, str]:
        current = self.source_health(source_id)
        failures = int(_row_get(current, "consecutive_failures", 0) or 0) + 1
        cooldown = ""
        if failures >= 2:
            seconds = min(21600, 900 * (2 ** min(5, failures - 2)))
            cooldown = (datetime.now(timezone.utc)+timedelta(seconds=seconds)).astimezone().isoformat(timespec="seconds")
        stamp = now_iso()
        with self.connect() as con:
            con.execute("""INSERT INTO source_health(source_id,consecutive_failures,cooldown_until,last_duration_ms,last_outcome,last_error,updated_at)
                           VALUES(?,?,?,?, 'ERROR', ?, ?)
                           ON CONFLICT(source_id) DO UPDATE SET consecutive_failures=excluded.consecutive_failures,cooldown_until=excluded.cooldown_until,last_duration_ms=excluded.last_duration_ms,last_outcome='ERROR',last_error=excluded.last_error,updated_at=excluded.updated_at""",
                        (int(source_id), failures, cooldown, max(0,int(duration_ms)), str(detail)[:1200], stamp))
        return failures, cooldown

    def provider_health(self) -> list[ProviderHealth]:
        with self.connect() as con: rows=con.execute("SELECT * FROM provider_health ORDER BY provider").fetchall()
        out=[]
        for row in rows:
            try: state=ProviderState(str(row["state"]))
            except Exception: state=ProviderState.UNKNOWN
            out.append(ProviderHealth(provider=str(row["provider"]),state=state,model=str(row["model"] or ""),detail=str(row["detail"] or ""),consecutive_failures=int(row["consecutive_failures"] or 0),success_count=int(row["success_count"] or 0),failure_count=int(row["failure_count"] or 0),cooldown_until=str(row["cooldown_until"] or ""),updated_at=str(row["updated_at"] or "")))
        return out

    def set_provider_health(self, health:ProviderHealth) -> None:
        with self.connect() as con: con.execute("""INSERT INTO provider_health(provider,state,model,detail,consecutive_failures,success_count,failure_count,cooldown_until,updated_at) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(provider) DO UPDATE SET state=excluded.state,model=excluded.model,detail=excluded.detail,consecutive_failures=excluded.consecutive_failures,success_count=excluded.success_count,failure_count=excluded.failure_count,cooldown_until=excluded.cooldown_until,updated_at=excluded.updated_at""",(health.provider,str(health.state),health.model,health.detail,int(health.consecutive_failures),int(health.success_count),int(health.failure_count),health.cooldown_until,health.updated_at or now_iso()))

    def ai_model_health(self, provider: str | None = None) -> list[AIModelHealth]:
        with self.connect() as con:
            if provider:
                rows = con.execute("SELECT * FROM ai_model_health WHERE provider=? ORDER BY model", (str(provider),)).fetchall()
            else:
                rows = con.execute("SELECT * FROM ai_model_health ORDER BY provider,model").fetchall()
        out: list[AIModelHealth] = []
        for row in rows:
            try:
                state = ProviderState(str(row["state"]))
            except Exception:
                state = ProviderState.UNKNOWN
            out.append(AIModelHealth(
                provider=str(row["provider"]), model=str(row["model"]), state=state, detail=str(row["detail"] or ""),
                consecutive_failures=int(row["consecutive_failures"] or 0), success_count=int(row["success_count"] or 0),
                failure_count=int(row["failure_count"] or 0), cooldown_until=str(row["cooldown_until"] or ""), updated_at=str(row["updated_at"] or ""),
            ))
        return out

    def set_ai_model_health(self, health: AIModelHealth) -> None:
        with self.connect() as con:
            con.execute("""INSERT INTO ai_model_health(provider,model,state,detail,consecutive_failures,success_count,failure_count,cooldown_until,updated_at)
                           VALUES(?,?,?,?,?,?,?,?,?)
                           ON CONFLICT(provider,model) DO UPDATE SET state=excluded.state,detail=excluded.detail,consecutive_failures=excluded.consecutive_failures,
                           success_count=excluded.success_count,failure_count=excluded.failure_count,cooldown_until=excluded.cooldown_until,updated_at=excluded.updated_at""",
                        (health.provider,health.model,str(health.state),health.detail,int(health.consecutive_failures),int(health.success_count),
                         int(health.failure_count),health.cooldown_until,health.updated_at or now_iso()))

    def clear_ai_model_cooldowns(self, provider: str | None = None) -> int:
        with self.connect() as con:
            if provider:
                cur = con.execute("UPDATE ai_model_health SET cooldown_until='' WHERE provider=? AND cooldown_until<>''", (str(provider),))
            else:
                cur = con.execute("UPDATE ai_model_health SET cooldown_until='' WHERE cooldown_until<>''")
            return int(cur.rowcount or 0)

    def audit(self, stream:str,event:str, *, channel_id:int|None=None,article_id:int|None=None,provider:str="",stage:str="",detail:str="",payload:Mapping[str,Any]|None=None) -> None:
        with self.connect() as con: con.execute("INSERT INTO audit_events(created_at,stream,event,channel_id,article_id,provider,stage,detail,payload_json) VALUES(?,?,?,?,?,?,?,?,?)",(now_iso(),str(stream),str(event),channel_id,article_id,str(provider),str(stage),str(detail)[:2000],json.dumps(dict(payload or {}),ensure_ascii=False,separators=(",",":"),default=str)))

    def mark_ready(self, article_id:int) -> None:
        row=self.get_article(article_id)
        if row is None: raise KeyError(article_id)
        canonical=str(row["canonical_source_url"] or "").strip()
        if not canonical.startswith(("http://","https://")):
            self.update_article(article_id,blocked_by=str(BlockedBy.SOURCE),last_error_code="SOURCE_MISSING",last_error_detail="Немає canonical source URL; READY/PUBLISH заборонено"); raise ValueError("SOURCE_MISSING")
        self.update_article(article_id,stage=str(Stage.READY),decision=str(Decision.PUBLISH),blocked_by=str(BlockedBy.NONE),ready_at=now_iso(),last_error_code="",last_error_detail="")

    def publication_guard(self, article_id:int) -> tuple[bool,str]:
        row=self.get_article(article_id)
        if row is None:return False,"ARTICLE_MISSING"
        if str(row["decision"])!=str(Decision.PUBLISH) or str(row["stage"])!=str(Stage.READY):return False,"NOT_READY"
        canonical=normalize_url(str(row["canonical_source_url"] or row["source_url"] or "").strip())
        if not canonical.startswith(("http://","https://")):return False,"SOURCE_MISSING"
        if canonical != str(row["canonical_source_url"] or ""):
            self.update_article(article_id,canonical_source_url=canonical)
        if not str(row["final_text"] or "").strip():return False,"TEXT_MISSING"
        channel=self.get_channel(int(row["channel_id"]))
        hours=int(channel.dedupe_window_hours if channel else 72)
        published=self.find_equivalent_article(int(row["channel_id"]),canonical,exclude_article_id=int(article_id),published_only=True,hours=hours)
        if published is not None:
            return False,f"ALREADY_PUBLISHED:{int(published['id'])}"
        return True,"OK"

    def mark_duplicate(self, article_id:int, duplicate_of:int, reason:str) -> None:
        detail=str(reason)[:2000]
        self.update_article(article_id,stage=str(Stage.DEDUPED),decision=str(Decision.DUPLICATE),blocked_by=str(BlockedBy.NONE),duplicate_of=int(duplicate_of),reject_reason=detail,status_detail=detail,last_error_code="",last_error_detail="",next_retry_at="")
        with self.connect() as con:
            con.execute("UPDATE jobs SET state='DONE',lease_owner='',lease_until='',error_code='',error_detail='',updated_at=? WHERE article_id=?",(now_iso(),int(article_id)))

    def telegram_delivery_state(self, article_id:int) -> dict[str,Any]:
        row=self.get_article(article_id)
        if row is None:return {}
        try: layout=json.loads(str(row["article_layout_json"] or "{}"))
        except Exception: layout={}
        if not isinstance(layout,dict):return {}
        value=layout.get("telegram_delivery")
        return dict(value) if isinstance(value,dict) else {}

    def record_telegram_media_delivery(self, article_id:int, message_ids:list[str]|tuple[str,...], *, caption_attached:bool=False, caption_message_id:str="") -> None:
        """Persist successfully sent media chunks before the final captioned chunk.

        For publications with >10 media, Telegram requires multiple groups. Earlier
        uncaptioned chunks are persisted so a retry does not duplicate them.
        """
        row=self.get_article(article_id)
        if row is None:raise KeyError(article_id)
        try: layout=json.loads(str(row["article_layout_json"] or "{}"))
        except Exception: layout={}
        if not isinstance(layout,dict):layout={}
        delivery=layout.get("telegram_delivery")
        if not isinstance(delivery,dict):delivery={}
        ids=[str(x) for x in message_ids if str(x).strip()]
        delivery.update({"media_message_ids":ids,"media_sent_at":now_iso(),"delivery_mode":"caption_media_v1","caption_attached":bool(caption_attached),"caption_message_id":str(caption_message_id or ""),"complete":False})
        layout["telegram_delivery"]=delivery
        self.update_article(article_id,article_layout_json=json.dumps(layout,ensure_ascii=False,separators=(",",":")),status_detail="Telegram media chunk sent; final captioned media pending")

    def mark_published(self, article_id:int, *, message_id:str,media_count:int=0,message_ids:list[str]|tuple[str,...]|None=None) -> None:
        ok,reason=self.publication_guard(article_id)
        if not ok:raise ValueError(reason)
        row=self.get_article(article_id)
        if row is None:raise KeyError(article_id)
        try: layout=json.loads(str(row["article_layout_json"] or "{}"))
        except Exception: layout={}
        if not isinstance(layout,dict):layout={}
        delivery=layout.get("telegram_delivery")
        if not isinstance(delivery,dict):delivery={}
        ids=[str(x) for x in (message_ids or [message_id]) if str(x).strip()]
        if str(message_id) and str(message_id) not in ids:ids.append(str(message_id))
        delivery.update({"message_ids":ids,"primary_message_id":str(message_id),"media_count":int(media_count),"expected_media_count":int(media_count),"completed_at":now_iso(),"complete":True})
        layout["telegram_delivery"]=delivery
        self.update_article(article_id,stage=str(Stage.PUBLISHED),decision=str(Decision.PUBLISH),blocked_by=str(BlockedBy.NONE),published_at=now_iso(),telegram_message_id=str(message_id),telegram_media_count=int(media_count),article_layout_json=json.dumps(layout,ensure_ascii=False,separators=(",",":")),status_detail="")
        with self.connect() as con: con.execute("UPDATE jobs SET state='DONE',lease_owner='',lease_until='',updated_at=? WHERE article_id=?",(now_iso(),int(article_id)))
