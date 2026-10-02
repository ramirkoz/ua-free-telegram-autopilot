from __future__ import annotations

import json
import sqlite3
from typing import Any

from .domain import DedupeProfile, EditorialRuntimeProfile
from .loghub import event
from .storage import now_iso


OPERATIONAL_RETENTION_DAYS = 7
HEAVY_PAYLOAD_RETENTION_DAYS = 30
_INSTALLED = False


def _apply_scientific_news_profile(store) -> int:
    """Apply the audited scientific/news profile through visible persisted settings.

    The target is selected only by the already-persisted channel role. No channel
    name, Telegram handle or numeric ID appears in runtime business logic.
    """
    key = "rc103_scientific_news_profile_v1"
    with store.connect() as con:
        done = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        if done and str(done[0] or "") == "1":
            return 0
        rows = con.execute(
            """SELECT c.id,p.selection_rules,p.rejection_rules,p.writing_rules,p.style_rules,
                      p.selector_extra_prompt,p.writer_extra_prompt,p.extra_instructions
                 FROM channels c JOIN channel_policies p ON p.channel_id=c.id
                WHERE c.channel_mode='editorial'
                  AND c.editorial_runtime_profile=?
                  AND c.dedupe_profile=?
                  AND c.dedupe_scientific_names=1
                  AND c.dedupe_compound_events=1""",
            (str(EditorialRuntimeProfile.STANDARD), str(DedupeProfile.SCIENTIFIC_NEWS)),
        ).fetchall()
        if not rows:
            return 0

        selection_block = (
            "[SCIENTIFIC_NEWS_RC103]\n"
            "Цільовий мікс каналу: AI приблизно 35–40%; robotics 15–20%; defense/Ukraine tech 10–15%; "
            "cybersecurity близько 10%; hardware близько 10%. Science+space разом не повинні домінувати "
            "(орієнтир до 25%), medicine/biology — рідкісний виняток (орієнтир до 10%). "
            "Перевага матеріалам із конкретним новим механізмом, продуктом, результатом, практичним наслідком або сильним відео."
        )
        rejection_block = (
            "[SCIENTIFIC_NEWS_RC103]\n"
            "Відхиляй вузьку академічну/медичну новину без технологічного або суспільно зрозумілого наслідку, "
            "PR без нового факту, повторні перекази однієї події та матеріали, цікаві лише дуже вузькій спеціальності."
        )
        selector_block = (
            "[SCIENTIFIC_NEWS_RC103] Prefer AI, robotics, defense technology, cybersecurity and hardware over generic science. "
            "Use science/space and medicine/biology as bounded supporting lanes, not the default feed. "
            "Prefer concrete mechanism + consequence + why-now and give extra weight to usable native video."
        )
        writer_block = (
            "[SCIENTIFIC_NEWS_RC103] Пиши 3 короткі абзаци, приблизно 450–600 знаків основного тексту. "
            "Перший абзац — що сталося; другий — як/чому це працює; третій — навіщо це читачеві. "
            "Без канцеляриту, без AI-слів-паразитів і без роздування слабкої новини."
        )
        extra_block = (
            "[SCIENTIFIC_NEWS_RC103] Робочий ритм: 8–12 сильних постів на добу у вікні 08:00–20:00, "
            "не частіше одного поста на 45 хвилин. Відео є позитивним сигналом, але не замінює редакційну цінність."
        )

        def add_once(value: str, block: str) -> str:
            base = str(value or "").strip()
            if "[SCIENTIFIC_NEWS_RC103]" in base:
                return base
            return (base + "\n\n" + block).strip() if base else block

        weights = [
            {"name": "AI", "weight": 38},
            {"name": "Robotics", "weight": 18},
            {"name": "Defense / Ukraine tech", "weight": 14},
            {"name": "Cybersecurity", "weight": 10},
            {"name": "Hardware", "weight": 10},
            {"name": "Science / Space", "weight": 7},
            {"name": "Medicine / Biology", "weight": 3},
        ]
        stamp = now_iso()
        for row in rows:
            con.execute(
                """UPDATE channels
                      SET min_publish_interval_minutes=45,publish_24h=0,publish_start='08:00',publish_end='20:00',
                          max_posts_per_cycle=2,published_dedupe_window_hours=720,dedupe_rare_terms=1,
                          editorial_weights_json=?,updated_at=?
                    WHERE id=?""",
                (json.dumps(weights, ensure_ascii=False, separators=(",", ":")), stamp, int(row["id"])),
            )
            con.execute(
                """UPDATE channel_policies
                      SET selection_rules=?,rejection_rules=?,writing_rules=?,style_rules=?,selector_extra_prompt=?,
                          writer_extra_prompt=?,extra_instructions=?,target_min_chars=450,target_max_chars=600,
                          media_policy='required',updated_at=?
                    WHERE channel_id=?""",
                (
                    add_once(row["selection_rules"], selection_block),
                    add_once(row["rejection_rules"], rejection_block),
                    add_once(row["writing_rules"], writer_block),
                    str(row["style_rules"] or ""),
                    add_once(row["selector_extra_prompt"], selector_block),
                    add_once(row["writer_extra_prompt"], writer_block),
                    add_once(row["extra_instructions"], extra_block),
                    stamp,
                    int(row["id"]),
                ),
            )
        con.execute(
            "INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, "1"),
        )
    if rows:
        event("editorial", "RC103 scientific-news profile applied", channels=len(rows))
    return len(rows)


def _compact_operational_database(store, *, retention_days: int = OPERATIONAL_RETENTION_DAYS, payload_days: int = HEAVY_PAYLOAD_RETENTION_DAYS) -> dict[str, int]:
    """Compact the live DB while preserving compact long-term identity/history."""
    retention_days = max(1, int(retention_days))
    payload_days = max(retention_days, int(payload_days))
    stale_mod = f"-{retention_days} days"
    payload_mod = f"-{payload_days} days"
    stats = {
        "retention_archived": 0,
        "jobs_pruned": 0,
        "audit_pruned": 0,
        "payload_compacted": 0,
        "vacuumed": 0,
    }
    with store.connect() as con:
        con.execute("CREATE INDEX IF NOT EXISTS idx_articles_discovered_recent ON articles(discovered_at DESC,id DESC)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_articles_review_recent ON articles(stage,discovered_at DESC,id DESC)")
        stale_ids = [
            int(row[0])
            for row in con.execute(
                """SELECT id FROM articles
                   WHERE stage<>'PUBLISHED'
                     AND datetime(discovered_at)<datetime('now',?)""",
                (stale_mod,),
            ).fetchall()
        ]
        if stale_ids:
            marks = ",".join("?" for _ in stale_ids)
            cur = con.execute(
                f"""UPDATE articles
                        SET stage='ARCHIVED',blocked_by='NONE',next_retry_at='',
                            last_error_code=CASE WHEN last_error_code='TELEGRAM_OUTCOME_UNKNOWN' THEN last_error_code ELSE 'RETENTION_7D' END,
                            last_error_detail=CASE WHEN last_error_code='TELEGRAM_OUTCOME_UNKNOWN' THEN last_error_detail ELSE 'Матеріал старший за 7 діб; прибрано з оперативної черги' END,
                            status_detail='Архівовано політикою 7-добового оперативного вікна',
                            raw_text='',draft_text='',media_json='[]',article_layout_json='{{}}',legacy_config_json=''
                      WHERE id IN ({marks})""",
                tuple(stale_ids),
            )
            stats["retention_archived"] = max(0, int(cur.rowcount))
            cur = con.execute(f"DELETE FROM jobs WHERE article_id IN ({marks})", tuple(stale_ids))
            stats["jobs_pruned"] += max(0, int(cur.rowcount))

        cur = con.execute(
            """UPDATE articles
                  SET raw_text='',draft_text='',media_json='[]',article_layout_json='{}',legacy_config_json=''
                WHERE datetime(discovered_at)<datetime('now',?)
                  AND stage IN ('PUBLISHED','ARCHIVED')
                  AND (raw_text<>'' OR draft_text<>'' OR media_json<>'[]' OR article_layout_json<>'{}' OR legacy_config_json<>'')""",
            (payload_mod,),
        )
        stats["payload_compacted"] = max(0, int(cur.rowcount))
        cur = con.execute("DELETE FROM audit_events WHERE datetime(created_at)<datetime('now',?)", (stale_mod,))
        stats["audit_pruned"] = max(0, int(cur.rowcount))
        cur = con.execute(
            """DELETE FROM jobs
                 WHERE article_id IN (
                     SELECT id FROM articles
                      WHERE datetime(discovered_at)<datetime('now',?)
                        AND stage IN ('PUBLISHED','ARCHIVED')
                 )""",
            (stale_mod,),
        )
        stats["jobs_pruned"] += max(0, int(cur.rowcount))
        con.execute("PRAGMA optimize")
        try:
            con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.Error:
            pass
        page_size = int(con.execute("PRAGMA page_size").fetchone()[0] or 4096)
        page_count = int(con.execute("PRAGMA page_count").fetchone()[0] or 0)
        freelist = int(con.execute("PRAGMA freelist_count").fetchone()[0] or 0)

    db_bytes = page_size * page_count
    if db_bytes >= 32 * 1024 * 1024 and page_count > 0 and freelist / page_count >= 0.15:
        with store.connect() as con:
            con.execute("VACUUM")
            con.execute("PRAGMA optimize")
        stats["vacuumed"] = 1
    event("storage", "RC103 database retention maintenance", **stats)
    return stats


def _install_store_contract() -> None:
    from .hardened_storage import HardenedV2Store

    original = HardenedV2Store.run_startup_maintenance

    def run_startup_maintenance(self):
        stats = dict(original(self))
        stats["scientific_news_profiles_applied"] = _apply_scientific_news_profile(self)
        stats.update(_compact_operational_database(self))
        return stats

    HardenedV2Store.run_startup_maintenance = run_startup_maintenance


def _install_editorial_review_contract() -> None:
    from .editorial_review import EditorialReviewService, ReviewItem

    def candidates(self, *, limit: int = 150):
        self.ensure_schema()
        with self.store.connect() as con:
            rows = con.execute(
                """SELECT a.id,a.channel_id,c.name channel_name,a.title,a.stage,a.blocked_by,
                          COALESCE(NULLIF(a.status_detail,''),NULLIF(a.last_error_detail,''),NULLIF(a.reject_reason,''),'') reason,
                          '' final_text,s.name source_name,a.discovered_at
                     FROM articles a
                     JOIN channels c ON c.id=a.channel_id
                     JOIN sources s ON s.id=a.source_id
                    WHERE TRIM(COALESCE(a.final_text,''))<>''
                      AND a.stage<>'PUBLISHED'
                      AND datetime(a.discovered_at)>=datetime('now','-7 days')
                      AND NOT EXISTS (
                          SELECT 1 FROM editorial_actions ea
                           WHERE ea.article_id=a.id
                             AND ea.id=(SELECT MAX(ea2.id) FROM editorial_actions ea2 WHERE ea2.article_id=a.id)
                             AND ea.action='reject'
                      )
                    ORDER BY datetime(a.discovered_at) DESC,a.id DESC LIMIT ?""",
                (max(1, min(300, int(limit))),),
            ).fetchall()
        return [
            ReviewItem(
                int(r["id"]), int(r["channel_id"]), str(r["channel_name"]), str(r["title"] or ""),
                str(r["stage"] or ""), str(r["blocked_by"] or ""), str(r["reason"] or ""), "",
                str(r["source_name"] or ""), str(r["discovered_at"] or ""),
            )
            for r in rows
        ]

    EditorialReviewService.candidates = candidates


def _install_ui_contract() -> None:
    from . import ui as ui_mod

    def refresh_queue(self):
        self.queue_tree.delete(*self.queue_tree.get_children())
        where = (
            "a.stage NOT IN ('PUBLISHED','ARCHIVED') AND a.decision NOT IN ('REJECT','DUPLICATE') "
            "AND datetime(a.discovered_at)>=datetime('now','-7 days')"
        )
        args: list[object] = []
        selected = self.queue_filter.get()
        if selected == "Готово":
            where += " AND a.stage='READY'"
        elif selected == "Заблоковано AI":
            where += " AND a.blocked_by='AI'"
        elif selected == "Заблоковано джерелом":
            where += " AND a.blocked_by='SOURCE'"
        elif selected == "Заблоковано медіа":
            where += " AND a.blocked_by='MEDIA'"
        elif selected == "Проблема якості":
            where += " AND a.blocked_by='QUALITY'"
        elif selected == "Очікує":
            where += " AND a.decision='PENDING'"
        with self.store.connect() as con:
            rows = con.execute(
                f"""SELECT a.id,c.name channel_name,a.stage,a.decision,a.blocked_by,a.title,a.last_error_detail,a.status_detail
                       FROM articles a JOIN channels c ON c.id=a.channel_id
                      WHERE {where} ORDER BY a.id DESC LIMIT 250""",
                args,
            ).fetchall()
        for row in rows:
            self.queue_tree.insert(
                "", "end", iid=str(row["id"]),
                values=(
                    row["id"], row["channel_name"], ui_mod.STAGE_UA.get(row["stage"], row["stage"]),
                    ui_mod.DECISION_UA.get(row["decision"], row["decision"]),
                    ui_mod.BLOCK_UA.get(row["blocked_by"], row["blocked_by"]), str(row["title"] or "")[:240],
                    str(row["last_error_detail"] or row["status_detail"] or "")[:260],
                ),
            )

    def refresh_editorial_review(self):
        if not hasattr(self, "editorial_tree"):
            return
        selected = self.editorial_tree.selection()
        wanted = selected[0] if selected else ""
        self.editorial_tree.delete(*self.editorial_tree.get_children())
        for item in self.review.candidates(limit=150):
            reason = item.reason or ("готовий, але ще не опублікований" if item.stage == "READY" else "очікує редакторського рішення")
            self.editorial_tree.insert(
                "", "end", iid=str(item.article_id),
                values=(
                    item.article_id, item.channel_name, ui_mod.STAGE_UA.get(item.stage, item.stage),
                    ui_mod.BLOCK_UA.get(item.blocked_by, item.blocked_by), item.title[:220], reason[:260], item.source_name[:120],
                ),
            )
        children = self.editorial_tree.get_children()
        if wanted in children:
            self.editorial_tree.selection_set(wanted)
            self.editorial_tree.focus(wanted)

    def refresh_history(self):
        self.history_tree.delete(*self.history_tree.get_children())
        with self.store.connect() as con:
            rows = con.execute(
                """SELECT a.id,c.name channel_name,a.stage,a.decision,a.title,a.published_at,a.canonical_source_url
                     FROM articles a JOIN channels c ON c.id=a.channel_id
                    WHERE (a.stage='PUBLISHED' OR a.decision IN ('REJECT','DUPLICATE'))
                      AND datetime(CASE WHEN a.published_at<>'' THEN a.published_at ELSE a.discovered_at END)>=datetime('now','-7 days')
                    ORDER BY a.id DESC LIMIT 300"""
            ).fetchall()
        for row in rows:
            status = "Опубліковано" if row["stage"] == "PUBLISHED" else ui_mod.DECISION_UA.get(row["decision"], row["decision"])
            self.history_tree.insert(
                "", "end",
                values=(row["id"], row["channel_name"], status, str(row["title"] or "")[:260], row["published_at"], row["canonical_source_url"]),
            )

    ui_mod.MainWindow.refresh_queue = refresh_queue
    ui_mod.MainWindow.refresh_editorial_review = refresh_editorial_review
    ui_mod.MainWindow.refresh_history = refresh_history


def _install_supervisor_contract() -> None:
    from .supervisor import SupervisorService

    original = SupervisorService._database_status

    def database_status(self) -> dict[str, Any]:
        base = dict(original(self))
        if not base.get("ok"):
            return base
        try:
            with self.store.connect() as con:
                page_size = int(con.execute("PRAGMA page_size").fetchone()[0] or 4096)
                page_count = int(con.execute("PRAGMA page_count").fetchone()[0] or 0)
                freelist = int(con.execute("PRAGMA freelist_count").fetchone()[0] or 0)
                active_7d = int(con.execute(
                    "SELECT COUNT(*) FROM articles WHERE datetime(discovered_at)>=datetime('now','-7 days')"
                ).fetchone()[0] or 0)
                stale = int(con.execute(
                    "SELECT COUNT(*) FROM articles WHERE stage<>'PUBLISHED' AND datetime(discovered_at)<datetime('now','-7 days')"
                ).fetchone()[0] or 0)
            size_bytes = page_size * page_count
            base.update(
                size_bytes=size_bytes,
                size_mb=round(size_bytes / (1024 * 1024), 2),
                page_count=page_count,
                freelist_pages=freelist,
                free_ratio=round((freelist / page_count) if page_count else 0.0, 4),
                operational_rows_7d=active_7d,
                stale_unpublished_over_7d=stale,
            )
        except sqlite3.Error as exc:
            base["metrics_error"] = str(exc)[:500]
        return base

    SupervisorService._database_status = database_status


def install_operational_contracts() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _install_store_contract()
    _install_editorial_review_contract()
    _install_ui_contract()
    _install_supervisor_contract()
    _INSTALLED = True
