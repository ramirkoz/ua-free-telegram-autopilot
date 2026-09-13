from __future__ import annotations

import json
from typing import Any

from .domain import ChannelMode, Stage
from .storage import V2Store, _clean_media_json, _layout_source_kind, _media_json_count, now_iso
from .urlnorm import normalize_url


class HardenedV2Store(V2Store):
    """V2 storage invariants that must hold regardless of publisher implementation.

    RC19 deliberately puts product contracts at the durable-data boundary:
    - fresh web media replaces the previous snapshot instead of accumulating URLs;
    - pending Telegram rows below media filter v3 are quarantined for a fresh read;
    - editorial rows can never reach READY with more than one media attachment.
    """

    def run_startup_maintenance(self) -> dict[str, int]:
        stats = dict(super().run_startup_maintenance())
        stats["sanitized_telegram_media_v3"] = self._sanitize_pre_rc19_telegram_media()
        stats["editorial_media_trimmed"] = self._enforce_editorial_single_media()
        return stats

    def insert_collected(
        self,
        *,
        channel_id: int,
        source_id: int,
        external_id: str,
        title: str,
        source_url: str,
        raw_text: str,
        content_hash: str = "",
        source_published_at: str = "",
        media_json: str = "[]",
        article_layout_json: str = "{}",
    ) -> int:
        is_telegram = _layout_source_kind(article_layout_json) == "telegram"
        fresh_media = _clean_media_json(media_json)

        # RC18 merged web media into the old set. That made promo banners and CDN
        # variants immortal across source polls. A non-empty fresh web extraction is
        # authoritative; transient empty extraction still keeps the previous set.
        if not is_telegram and _media_json_count(fresh_media) > 0:
            canonical = normalize_url(str(source_url or "").strip())
            with self.connect() as con:
                row = con.execute(
                    "SELECT id,stage FROM articles WHERE channel_id=? AND source_id=? AND external_id=?",
                    (int(channel_id), int(source_id), str(external_id)),
                ).fetchone()
                if row is None and canonical:
                    row = con.execute(
                        "SELECT id,stage FROM articles WHERE channel_id=? AND canonical_source_url=? ORDER BY id DESC LIMIT 1",
                        (int(channel_id), canonical),
                    ).fetchone()
                if row is not None and str(row["stage"]) != str(Stage.PUBLISHED):
                    con.execute("UPDATE articles SET media_json='[]' WHERE id=?", (int(row["id"]),))

        article_id = super().insert_collected(
            channel_id=channel_id,
            source_id=source_id,
            external_id=external_id,
            title=title,
            source_url=source_url,
            raw_text=raw_text,
            content_hash=content_hash,
            source_published_at=source_published_at,
            media_json=fresh_media,
            article_layout_json=article_layout_json,
        )
        self._enforce_single_article_if_editorial(article_id)
        return article_id

    def mark_ready(self, article_id: int) -> None:
        self._enforce_single_article_if_editorial(article_id)
        super().mark_ready(article_id)

    def _enforce_single_article_if_editorial(self, article_id: int) -> bool:
        row = self.get_article(int(article_id))
        if row is None:
            return False
        channel = self.get_channel(int(row["channel_id"]))
        if channel is None or channel.mode != ChannelMode.EDITORIAL:
            return False
        return self._trim_article_to_one_media(int(article_id), row)

    def _trim_article_to_one_media(self, article_id: int, row: Any | None = None) -> bool:
        row = row or self.get_article(int(article_id))
        if row is None:
            return False
        cleaned = _clean_media_json(str(row["media_json"] or "[]"))
        try:
            media = json.loads(cleaned)
        except Exception:
            media = []
        media = list(media) if isinstance(media, list) else []
        trimmed_media = media[:1]

        try:
            layout = json.loads(str(row["article_layout_json"] or "{}"))
        except Exception:
            layout = {}
        if not isinstance(layout, dict):
            layout = {}
        blocks = list(layout.get("blocks") or []) if isinstance(layout.get("blocks"), list) else []
        kept_media = False
        new_blocks: list[Any] = []
        for block in blocks:
            if isinstance(block, dict) and str(block.get("type") or "") == "media":
                if kept_media:
                    continue
                kept_media = True
            new_blocks.append(block)
        if blocks:
            layout["blocks"] = new_blocks
        tg = layout.get("telegram")
        if isinstance(tg, dict):
            tg["media_count"] = min(1, len(trimmed_media))
            tg["media_group"] = False
            tg["stitched"] = False

        next_media = json.dumps(trimmed_media, ensure_ascii=False, separators=(",", ":"))
        next_layout = json.dumps(layout, ensure_ascii=False, separators=(",", ":"))
        changed = next_media != str(row["media_json"] or "[]") or next_layout != str(row["article_layout_json"] or "{}")
        if changed:
            with self.connect() as con:
                con.execute(
                    "UPDATE articles SET media_json=?,article_layout_json=? WHERE id=?",
                    (next_media, next_layout, int(article_id)),
                )
        return changed

    def _enforce_editorial_single_media(self) -> int:
        changed = 0
        with self.connect() as con:
            rows = con.execute(
                """
                SELECT a.* FROM articles a
                JOIN channels c ON c.id=a.channel_id
                WHERE c.channel_mode='editorial' AND a.stage<>'PUBLISHED'
                """
            ).fetchall()
        for row in rows:
            if self._trim_article_to_one_media(int(row["id"]), row):
                changed += 1
        return changed

    def _sanitize_pre_rc19_telegram_media(self) -> int:
        key = "rc19_telegram_media_filter_reset_v1"
        with self.connect() as con:
            done = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
            if done and str(done[0] or "") == "1":
                return 0
        changed = 0
        stamp = now_iso()
        with self.transaction() as con:
            try:
                con.execute("BEGIN IMMEDIATE")
                rows = con.execute(
                    "SELECT id,channel_id,article_layout_json FROM articles WHERE stage<>'PUBLISHED'"
                ).fetchall()
                for row in rows:
                    try:
                        layout = json.loads(str(row["article_layout_json"] or "{}"))
                    except Exception:
                        layout = {}
                    if not isinstance(layout, dict) or str(layout.get("source_kind") or "").casefold() != "telegram":
                        continue
                    tg = layout.get("telegram")
                    try:
                        filter_version = int(tg.get("media_filter_version") or 0) if isinstance(tg, dict) else 0
                    except Exception:
                        filter_version = 0
                    if filter_version >= 3:
                        continue
                    if isinstance(tg, dict):
                        tg["media_count"] = 0
                        tg["media_group"] = False
                        tg["media_filter_version"] = 0
                    layout["blocks"] = [
                        block for block in list(layout.get("blocks") or [])
                        if not (isinstance(block, dict) and str(block.get("type") or "") == "media")
                    ]
                    article_id = int(row["id"])
                    channel_id = int(row["channel_id"])
                    con.execute(
                        """UPDATE articles SET media_json='[]',article_layout_json=?,stage='COLLECTED',decision='PENDING',
                           blocked_by='MEDIA',ready_at='',final_text='',last_error_code='TELEGRAM_MEDIA_REFRESH_REQUIRED',
                           last_error_detail='RC19 requires a fresh same-widget Telegram media snapshot',next_retry_at=''
                           WHERE id=?""",
                        (json.dumps(layout, ensure_ascii=False, separators=(",", ":")), article_id),
                    )
                    con.execute(
                        """INSERT INTO jobs(article_id,channel_id,job_type,state,priority,available_at,lease_owner,lease_until,attempts,error_code,error_detail,created_at,updated_at)
                           VALUES(?,?,'process','WAITING',10,?,'','',0,'TELEGRAM_MEDIA_REFRESH_REQUIRED','Waiting for RC19 source refresh',?,?)
                           ON CONFLICT(article_id,job_type) DO UPDATE SET state='WAITING',priority=MIN(jobs.priority,10),available_at=excluded.available_at,
                           lease_owner='',lease_until='',attempts=0,error_code=excluded.error_code,error_detail=excluded.error_detail,updated_at=excluded.updated_at""",
                        (article_id, channel_id, stamp, stamp, stamp),
                    )
                    changed += 1
                con.execute(
                    "INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, "1"),
                )
                con.commit()
            except Exception:
                con.rollback()
                raise
        return changed
