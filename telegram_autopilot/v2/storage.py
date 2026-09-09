from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping

from . import V2_SCHEMA_VERSION
from .domain import BlockedBy, ChannelConfig, ChannelMode, ChannelPolicy, Decision, ProviderHealth, ProviderState, Stage


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
 channel_mode TEXT NOT NULL DEFAULT 'editorial',editorial_profile TEXT NOT NULL DEFAULT '',include_source_link INTEGER NOT NULL DEFAULT 1,
 source_link_required INTEGER NOT NULL DEFAULT 1,poll_interval_minutes INTEGER NOT NULL DEFAULT 5,poll_immediate INTEGER NOT NULL DEFAULT 0,
 min_publish_interval_minutes INTEGER NOT NULL DEFAULT 10,dedupe_window_hours INTEGER NOT NULL DEFAULT 72,max_age_hours INTEGER NOT NULL DEFAULT 24,
 max_posts_per_cycle INTEGER NOT NULL DEFAULT 3,publish_24h INTEGER NOT NULL DEFAULT 0,publish_start TEXT NOT NULL DEFAULT '07:00',
 publish_end TEXT NOT NULL DEFAULT '00:00',publish_immediately INTEGER NOT NULL DEFAULT 0,topic_balance_enabled INTEGER NOT NULL DEFAULT 1,
 topic_daily_limit INTEGER NOT NULL DEFAULT 2,related_spacing_posts INTEGER NOT NULL DEFAULT 5,editorial_weights_json TEXT NOT NULL DEFAULT '[]',
 language_mode TEXT NOT NULL DEFAULT 'ukru_to_uk',media_enrichment_mode TEXT NOT NULL DEFAULT 'auto',media_first_allowed INTEGER NOT NULL DEFAULT 1,
 media_min_text_chars INTEGER NOT NULL DEFAULT 500,legacy_config_json TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL,updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS channel_policies (
 channel_id INTEGER PRIMARY KEY REFERENCES channels(id) ON DELETE CASCADE,enabled INTEGER NOT NULL DEFAULT 1,purpose TEXT NOT NULL DEFAULT '',
 audience TEXT NOT NULL DEFAULT '',selection_rules TEXT NOT NULL DEFAULT '',rejection_rules TEXT NOT NULL DEFAULT '',writing_rules TEXT NOT NULL DEFAULT '',
 style_rules TEXT NOT NULL DEFAULT '',positive_examples TEXT NOT NULL DEFAULT '',negative_examples TEXT NOT NULL DEFAULT '',extra_instructions TEXT NOT NULL DEFAULT '',
 selector_extra_prompt TEXT NOT NULL DEFAULT '',writer_extra_prompt TEXT NOT NULL DEFAULT '',media_policy TEXT NOT NULL DEFAULT 'required',
 target_min_chars INTEGER NOT NULL DEFAULT 300,target_max_chars INTEGER NOT NULL DEFAULT 750,updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sources (
 id INTEGER PRIMARY KEY,channel_id INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,kind TEXT NOT NULL,name TEXT NOT NULL,url TEXT NOT NULL,
 enabled INTEGER NOT NULL DEFAULT 1,initialized INTEGER NOT NULL DEFAULT 0,priority INTEGER NOT NULL DEFAULT 100,last_checked_at TEXT NOT NULL DEFAULT '',
 last_error TEXT NOT NULL DEFAULT '',legacy_config_json TEXT NOT NULL DEFAULT '{}',UNIQUE(channel_id,url)
);
CREATE INDEX IF NOT EXISTS idx_sources_channel ON sources(channel_id,enabled,priority,id);
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
CREATE TABLE IF NOT EXISTS feedback (
 article_id INTEGER PRIMARY KEY REFERENCES articles(id) ON DELETE CASCADE,channel_id INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
 telegram_message_id TEXT NOT NULL DEFAULT '',checked_at TEXT NOT NULL DEFAULT '',published_at TEXT NOT NULL DEFAULT '',views INTEGER NOT NULL DEFAULT 0,
 forwards INTEGER NOT NULL DEFAULT 0,replies INTEGER NOT NULL DEFAULT 0,likes INTEGER NOT NULL DEFAULT 0,dislikes INTEGER NOT NULL DEFAULT 0,
 fires INTEGER NOT NULL DEFAULT 0,other_reactions INTEGER NOT NULL DEFAULT 0,legacy_config_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_feedback_channel ON feedback(channel_id,published_at DESC);
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
                con.executescript(SCHEMA); con.execute("INSERT INTO meta(key,value) VALUES('schema_version',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(str(V2_SCHEMA_VERSION),))

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
            media_policy=str(_row_get(p,"media_policy","required") or "required"),target_min_chars=int(_row_get(p,"target_min_chars",300) or 300),target_max_chars=int(_row_get(p,"target_max_chars",750) or 750),
        )
        mode=ChannelMode.MONITORING if str(row["channel_mode"]).casefold()=="monitoring" else ChannelMode.EDITORIAL
        return ChannelConfig(
            id=int(row["id"]),name=str(row["name"]),telegram_chat_id=str(row["telegram_chat_id"] or ""),enabled=_bool(row["enabled"],True),mode=mode,
            editorial_profile=str(row["editorial_profile"] or ""),include_source_link=_bool(row["include_source_link"],True),source_link_required=_bool(row["source_link_required"],True),
            poll_interval_minutes=int(row["poll_interval_minutes"] or 5),poll_immediate=_bool(row["poll_immediate"],False),min_publish_interval_minutes=int(row["min_publish_interval_minutes"] or 10),
            dedupe_window_hours=int(row["dedupe_window_hours"] or 72),max_age_hours=int(row["max_age_hours"] or 24),max_posts_per_cycle=int(row["max_posts_per_cycle"] or 3),
            publish_24h=_bool(row["publish_24h"],False),publish_start=str(row["publish_start"] or "07:00"),publish_end=str(row["publish_end"] or "00:00"),publish_immediately=_bool(row["publish_immediately"],False),
            topic_balance_enabled=_bool(row["topic_balance_enabled"],True),topic_daily_limit=int(row["topic_daily_limit"] or 2),related_spacing_posts=int(row["related_spacing_posts"] or 5),
            editorial_weights_json=str(row["editorial_weights_json"] or "[]"),language_mode=str(row["language_mode"] or "ukru_to_uk"),media_enrichment_mode=str(row["media_enrichment_mode"] or "auto"),
            media_first_allowed=_bool(row["media_first_allowed"],True),media_min_text_chars=int(row["media_min_text_chars"] or 500),policy=policy,
        )

    def save_channel(self, cfg: ChannelConfig) -> None:
        stamp=now_iso()
        with self.transaction() as con:
            try:
                con.execute("BEGIN IMMEDIATE")
                con.execute("""UPDATE channels SET name=?,telegram_chat_id=?,enabled=?,channel_mode=?,editorial_profile=?,include_source_link=?,source_link_required=?,poll_interval_minutes=?,poll_immediate=?,min_publish_interval_minutes=?,dedupe_window_hours=?,max_age_hours=?,max_posts_per_cycle=?,publish_24h=?,publish_start=?,publish_end=?,publish_immediately=?,topic_balance_enabled=?,topic_daily_limit=?,related_spacing_posts=?,editorial_weights_json=?,language_mode=?,media_enrichment_mode=?,media_first_allowed=?,media_min_text_chars=?,updated_at=? WHERE id=?""",
                    (cfg.name,cfg.telegram_chat_id,int(cfg.enabled),str(cfg.mode),cfg.editorial_profile,int(cfg.include_source_link),int(cfg.source_link_required),int(cfg.poll_interval_minutes),int(cfg.poll_immediate),int(cfg.min_publish_interval_minutes),int(cfg.dedupe_window_hours),int(cfg.max_age_hours),int(cfg.max_posts_per_cycle),int(cfg.publish_24h),cfg.publish_start,cfg.publish_end,int(cfg.publish_immediately),int(cfg.topic_balance_enabled),int(cfg.topic_daily_limit),int(cfg.related_spacing_posts),cfg.editorial_weights_json,cfg.language_mode,cfg.media_enrichment_mode,int(cfg.media_first_allowed),int(cfg.media_min_text_chars),stamp,int(cfg.id)))
                p=cfg.policy
                con.execute("""INSERT INTO channel_policies(channel_id,enabled,purpose,audience,selection_rules,rejection_rules,writing_rules,style_rules,positive_examples,negative_examples,extra_instructions,selector_extra_prompt,writer_extra_prompt,media_policy,target_min_chars,target_max_chars,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(channel_id) DO UPDATE SET enabled=excluded.enabled,purpose=excluded.purpose,audience=excluded.audience,selection_rules=excluded.selection_rules,rejection_rules=excluded.rejection_rules,writing_rules=excluded.writing_rules,style_rules=excluded.style_rules,positive_examples=excluded.positive_examples,negative_examples=excluded.negative_examples,extra_instructions=excluded.extra_instructions,selector_extra_prompt=excluded.selector_extra_prompt,writer_extra_prompt=excluded.writer_extra_prompt,media_policy=excluded.media_policy,target_min_chars=excluded.target_min_chars,target_max_chars=excluded.target_max_chars,updated_at=excluded.updated_at""",
                    (cfg.id,int(p.enabled),p.purpose,p.audience,p.selection_rules,p.rejection_rules,p.writing_rules,p.style_rules,p.positive_examples,p.negative_examples,p.extra_instructions,p.selector_extra_prompt,p.writer_extra_prompt,p.media_policy,int(p.target_min_chars),int(p.target_max_chars),stamp))
                con.commit()
            except Exception: con.rollback(); raise

    def sources_for_channel(self, channel_id: int, *, enabled_only: bool=True) -> list[sqlite3.Row]:
        clause=" AND enabled=1" if enabled_only else ""
        with self.connect() as con: return list(con.execute(f"SELECT * FROM sources WHERE channel_id=?{clause} ORDER BY priority,id",(int(channel_id),)))

    def get_article(self, article_id: int) -> sqlite3.Row | None:
        with self.connect() as con: return con.execute("SELECT a.*,s.name AS source_name,s.url AS source_root_url FROM articles a JOIN sources s ON s.id=a.source_id WHERE a.id=?",(int(article_id),)).fetchone()

    def recent_candidates(self, channel_id: int, *, article_id: int, hours: int=72, limit: int=120) -> list[sqlite3.Row]:
        with self.connect() as con:
            return list(con.execute("""SELECT a.*,s.name AS source_name FROM articles a JOIN sources s ON s.id=a.source_id WHERE a.channel_id=? AND a.id<>? AND datetime(a.discovered_at)>=datetime('now',?) AND a.stage<>'ARCHIVED' ORDER BY a.id DESC LIMIT ?""",(int(channel_id),int(article_id),f"-{max(1,int(hours))} hours",max(1,int(limit)))))

    def last_published_at(self, channel_id: int) -> str:
        with self.connect() as con:
            row=con.execute("SELECT published_at FROM articles WHERE channel_id=? AND stage='PUBLISHED' AND published_at<>'' ORDER BY datetime(published_at) DESC,id DESC LIMIT 1",(int(channel_id),)).fetchone()
            return str(row[0] or "") if row else ""

    def ready_articles(self, channel_id: int, limit: int=100) -> list[sqlite3.Row]:
        with self.connect() as con: return list(con.execute("SELECT a.*,s.name AS source_name FROM articles a JOIN sources s ON s.id=a.source_id WHERE a.channel_id=? AND a.stage='READY' AND a.decision='PUBLISH' ORDER BY datetime(CASE WHEN a.source_published_at<>'' THEN a.source_published_at ELSE a.discovered_at END) DESC,a.id DESC LIMIT ?",(int(channel_id),max(1,int(limit)))))

    def update_article(self, article_id: int, **fields: Any) -> None:
        allowed={"title","source_url","canonical_source_url","raw_text","content_hash","source_published_at","stage","decision","blocked_by","status_detail","reject_reason","duplicate_of","event_key","event_summary","editorial_category","editorial_value_score","tags_json","topic_major","topic_minor","draft_text","final_text","ai_provider","ai_model","media_json","article_layout_json","ready_at","published_at","telegram_message_id","telegram_media_count","last_error_code","last_error_detail","retry_count","next_retry_at","legacy_status"}
        clean={k:v for k,v in fields.items() if k in allowed}
        if not clean: return
        assignments=",".join(f"{k}=?" for k in clean)
        with self.connect() as con: con.execute(f"UPDATE articles SET {assignments} WHERE id=?",tuple(clean.values())+(int(article_id),))

    def insert_collected(self, *, channel_id:int,source_id:int,external_id:str,title:str,source_url:str,raw_text:str,content_hash:str="",source_published_at:str="",media_json:str="[]",article_layout_json:str="{}") -> int:
        stamp=now_iso(); canonical=str(source_url or "").strip()
        with self.transaction() as con:
            try:
                con.execute("BEGIN IMMEDIATE"); row=con.execute("SELECT id FROM articles WHERE channel_id=? AND source_id=? AND external_id=?",(int(channel_id),int(source_id),str(external_id))).fetchone()
                if row: con.commit(); return int(row["id"])
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
                row=con.execute("""SELECT j.* FROM jobs j JOIN articles a ON a.id=j.article_id WHERE j.state IN ('QUEUED','WAITING') AND datetime(j.available_at)<=datetime('now') AND a.decision='PENDING'"""+channel_sql+" ORDER BY j.priority ASC,CASE WHEN a.source_published_at<>'' THEN datetime(a.source_published_at) ELSE datetime(a.discovered_at) END DESC,j.id ASC LIMIT 1",tuple(args)).fetchone()
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
        if not str(row["canonical_source_url"] or "").strip().startswith(("http://","https://")):return False,"SOURCE_MISSING"
        if not str(row["final_text"] or "").strip():return False,"TEXT_MISSING"
        return True,"OK"

    def mark_published(self, article_id:int, *, message_id:str,media_count:int=0) -> None:
        ok,reason=self.publication_guard(article_id)
        if not ok:raise ValueError(reason)
        self.update_article(article_id,stage=str(Stage.PUBLISHED),decision=str(Decision.PUBLISH),blocked_by=str(BlockedBy.NONE),published_at=now_iso(),telegram_message_id=str(message_id),telegram_media_count=int(media_count))
        with self.connect() as con: con.execute("UPDATE jobs SET state='DONE',lease_owner='',lease_until='',updated_at=? WHERE article_id=?",(now_iso(),int(article_id)))
