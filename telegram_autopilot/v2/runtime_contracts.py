from __future__ import annotations

import threading
from datetime import datetime, timezone

from .loghub import event
from .storage import now_iso


_PUBLISH_LOCK = threading.RLock()
_INSTALLED = False


def _latest_human_action(store, article_id: int) -> str:
    try:
        with store.connect() as con:
            row = con.execute(
                "SELECT action FROM editorial_actions WHERE article_id=? ORDER BY id DESC LIMIT 1",
                (int(article_id),),
            ).fetchone()
        return str(row[0] or "").strip().casefold() if row else ""
    except Exception:
        return ""


def _human_approved(store, article_id: int) -> bool:
    return _latest_human_action(store, article_id) in {"approve", "edit", "publish_now", "publish_attempt"}


def _enforce_terminal_human_rejects(store) -> int:
    """Re-assert explicit human rejects after any automatic recovery pass."""
    try:
        with store.connect() as con:
            rows = con.execute(
                """SELECT a.id
                   FROM articles a
                   JOIN editorial_actions ea ON ea.article_id=a.id
                   WHERE ea.id=(SELECT MAX(ea2.id) FROM editorial_actions ea2 WHERE ea2.article_id=a.id)
                     AND ea.action='reject'
                     AND (a.stage<>'ARCHIVED' OR a.decision<>'REJECT' OR a.blocked_by<>'NONE')"""
            ).fetchall()
            ids = [int(row[0]) for row in rows]
            if not ids:
                return 0
            marks = ",".join("?" for _ in ids)
            con.execute(
                f"""UPDATE articles SET stage='ARCHIVED',decision='REJECT',blocked_by='NONE',
                    last_error_code='',last_error_detail='',next_retry_at='',
                    status_detail=CASE WHEN status_detail='' THEN 'Відхилено редактором вручну' ELSE status_detail END
                    WHERE id IN ({marks})""",
                tuple(ids),
            )
            con.execute(
                f"""UPDATE jobs SET state='DONE',lease_owner='',lease_until='',error_code='HUMAN_REJECT',
                    error_detail='Explicit human reject is terminal',updated_at=? WHERE article_id IN ({marks})""",
                (now_iso(), *ids),
            )
        event("editorial", "RC102 terminal human rejects reasserted", count=len(ids))
        return len(ids)
    except Exception as exc:
        event("editorial", "RC102 terminal reject reassert failed", level=40, detail=str(exc)[:700])
        return 0


def _install_publisher_contract() -> None:
    from . import editorial as editorial_mod
    from .publisher import Publisher

    original_can_publish_now = Publisher.can_publish_now
    original_publish_one = Publisher.publish_one

    def can_publish_now(self, channel_id: int, *, force: bool = False):
        if force or bool(getattr(self, "_rc102_force_publish", False)):
            channel = self.store.get_channel(channel_id)
            if channel is None:
                return False, "CHANNEL_MISSING"
            if not channel.enabled:
                return False, "CHANNEL_DISABLED"
            return True, "OK"
        return original_can_publish_now(self, channel_id)

    def publish_one(self, article_id: int, heartbeat=None, *, force: bool = False):
        approved = _human_approved(self.store, int(article_id))
        with _PUBLISH_LOCK:
            previous_force = bool(getattr(self, "_rc102_force_publish", False))
            previous_qa = editorial_mod.prepublish_quality_issues
            try:
                self._rc102_force_publish = bool(force)
                if approved:
                    editorial_mod.prepublish_quality_issues = lambda _channel, _article, _text: ()
                    event("editorial", "HUMAN_APPROVE_OVERRIDE", channel_id=int((self.store.get_article(article_id) or {"channel_id": 0})["channel_id"]), article_id=int(article_id))
                result = original_publish_one(self, int(article_id), heartbeat=heartbeat)
            finally:
                editorial_mod.prepublish_quality_issues = previous_qa
                self._rc102_force_publish = previous_force
        if approved:
            row = self.store.get_article(int(article_id))
            channel_id = int(row["channel_id"] if row is not None else 0)
            if result == "PUBLISHED":
                event("editorial", "HUMAN_PUBLISH_SUCCESS", channel_id=channel_id, article_id=int(article_id), result=result)
            else:
                event("editorial", "HUMAN_PUBLISH_BLOCKED", level=30, channel_id=channel_id, article_id=int(article_id), result=str(result))
        return result

    Publisher.can_publish_now = can_publish_now
    Publisher.publish_one = publish_one


def _install_ui_contract() -> None:
    import threading as _threading
    from tkinter import messagebox
    from .ui import MainWindow

    def editorial_publish_now(self):
        article_id = self._selected_editorial_article()
        if article_id is None:
            return
        try:
            self.review.approve(article_id)
        except Exception as exc:
            messagebox.showerror("Редакторська черга", str(exc), parent=self)
            return
        self.status.set(f"Публікую #{article_id} вручну…")

        def work():
            try:
                result = self.runtime.publisher.publish_one(article_id, force=True)
                self.review.record_publish_now(article_id, result)
                msg = f"Матеріал #{article_id}: {result}"
            except Exception as exc:
                msg = f"Помилка ручної публікації #{article_id}: {exc}"
            self.after(0, lambda: (
                self.status.set(msg), self.refresh_editorial_review(), self.refresh_history(), self.refresh_learning()
            ))

        _threading.Thread(target=work, daemon=True, name=f"V2-Editorial-Publish-{article_id}").start()

    original_reject = MainWindow.editorial_reject

    def editorial_reject(self):
        article_id = self._selected_editorial_article()
        original_reject(self)
        if article_id is not None:
            try:
                row = self.store.get_article(int(article_id))
                if row is not None and str(row["stage"]) == "ARCHIVED" and str(row["decision"]) == "REJECT":
                    self.editorial_tree.delete(str(article_id))
            except Exception:
                pass

    MainWindow.editorial_publish_now = editorial_publish_now
    MainWindow.editorial_reject = editorial_reject


def _install_recovery_contract() -> None:
    from .hardened_storage import HardenedV2Store
    from .ready_backlog import ReadyBacklogStore

    original_hardened_maintenance = HardenedV2Store.run_startup_maintenance
    original_recover_nonrequired = ReadyBacklogStore._recover_nonrequired_media_backlog

    def hardened_maintenance(self):
        stats = original_hardened_maintenance(self)
        stats["terminal_human_rejects_reasserted"] = _enforce_terminal_human_rejects(self)
        return stats

    def recover_nonrequired(self):
        changed = original_recover_nonrequired(self)
        _enforce_terminal_human_rejects(self)
        return changed

    HardenedV2Store.run_startup_maintenance = hardened_maintenance
    ReadyBacklogStore._recover_nonrequired_media_backlog = recover_nonrequired


def _install_supervisor_contract() -> None:
    from .ready_backlog import ReadyBacklogSupervisor
    from .supervisor import Incident

    original_build_snapshot = ReadyBacklogSupervisor.build_snapshot
    original_evaluate = ReadyBacklogSupervisor.evaluate

    def build_snapshot(self):
        # Preserve ready_blockers, ready_publishable and ready_permanent_blocked from the canonical snapshot.
        snapshot = original_build_snapshot(self)
        stats_all = dict(snapshot.get("channel_stats") or {})
        with self.store.connect() as con:
            for channel_id, raw in list(stats_all.items()):
                stats = dict(raw or {})
                row = con.execute(
                    """SELECT COUNT(*) n,MIN(ea.created_at) oldest
                       FROM articles a
                       JOIN editorial_actions ea ON ea.article_id=a.id
                       WHERE a.channel_id=? AND a.stage='READY' AND a.decision='PUBLISH'
                         AND ea.id=(SELECT MAX(ea2.id) FROM editorial_actions ea2 WHERE ea2.article_id=a.id)
                         AND ea.action IN ('approve','edit','publish_attempt')""",
                    (int(channel_id),),
                ).fetchone()
                stats["human_approved_pending"] = int(row["n"] or 0) if row else 0
                stats["human_approved_oldest_at"] = str(row["oldest"] or "") if row else ""
                stats_all[str(channel_id)] = stats
        snapshot["channel_stats"] = stats_all
        return snapshot

    def evaluate(self, snapshot, cfg=None):
        incidents = list(original_evaluate(self, snapshot, cfg))
        now = datetime.now(timezone.utc).timestamp()
        for cid, stats in dict(snapshot.get("channel_stats") or {}).items():
            pending = int(stats.get("human_approved_pending") or 0)
            oldest = self._parse_iso(str(stats.get("human_approved_oldest_at") or ""))
            age = max(0.0, now - oldest) if oldest is not None else 0.0
            if pending > 0 and age >= 300.0:
                name = str(stats.get("name") or cid)
                incidents.append(Incident(
                    "WARNING",
                    f"APPROVED_NOT_PUBLISHED_{cid}",
                    f"Погоджений редактором матеріал у «{name}» не опубліковано",
                    f"human_approved_pending={pending}; oldest_age={int(age)//60} хв; READY blockers={stats.get('ready_blockers') or {}}.",
                ))
        return incidents

    ReadyBacklogSupervisor.build_snapshot = build_snapshot
    ReadyBacklogSupervisor.evaluate = evaluate


def _install_ai_efficiency_contract() -> None:
    from . import editorial as ed
    from .domain import Decision

    def combined_select(self, channel, article):
        p = channel.policy
        learning = self.learning.topic_assessment(channel.id, article)
        if learning.hard_suppress:
            reason = (
                f"LEARNING_ADMIN_DISLIKE: very close recent editor-disliked story #{learning.matched_article_id}; "
                f"similarity={learning.matched_similarity:.2f}"
            )
            event("learning", "topic hard suppress", channel_id=channel.id, article_id=int(ed._v(article, "id", 0) or 0), detail=reason)
            return ed.EditorialOutcome(Decision.REJECT, reason=reason, fit_score=0)
        topic_memory = self.learning.topic_memory_block(channel.id, article)
        prompt = f"""Ти CHANNEL-FIT + EDITORIAL-VALUE SELECTOR Telegram-автопілота RC102. Зроби ОДНЕ рішення одним викликом.
PURPOSE: {p.purpose}\nAUDIENCE: {p.audience}\nSELECTION: {p.selection_rules}\nEXCLUSIONS: {p.rejection_rules}\nEXTRA: {p.selector_extra_prompt}
{topic_memory}
SOURCE NAME: {ed._clean(ed._v(article, 'source_name', ''), 300)}\nSOURCE TITLE: {ed._clean(ed._v(article, 'title', ''), 700)}\nSOURCE:\n{ed._source_pack(article, 3600)}
Оціни channel fit і value одночасно. Усі оцінки 0..100. Навіть для reject поверни всі поля.
Поверни ТІЛЬКИ JSON: {{"decision":"publish" або "reject","fit_score":0,"reason":"коротко","angle":"кут","topic_tags":["..."],"novelty":0,"consequence_or_insight":0,"mechanism":0,"reader_payoff":0,"retellability":0,"concrete_stakes":0,"why_now":0,"curiosity_only":false,"commercial_mechanism":0,"consumer_behavior":0,"creative_execution":0,"measurable_result":0,"strategic_transferability":0,"general_interest":0,"culture_signal":0,"surprise_or_conflict":0,"consumer_relevance":0}}"""

        commercial = ed._is_commercial_editorial(channel)
        required = (
            ("commercial_mechanism", "consumer_behavior", "creative_execution", "measurable_result", "strategic_transferability", "why_now", "general_interest", "retellability", "culture_signal", "surprise_or_conflict", "consumer_relevance")
            if commercial else
            ("novelty", "consequence_or_insight", "mechanism", "reader_payoff", "retellability", "concrete_stakes", "why_now")
        )

        def parse(raw: str):
            obj = ed._parse_json(raw)
            decision = str(obj.get("decision") or "").casefold()
            if decision not in {"publish", "reject"}:
                raise ValueError("invalid decision")
            if decision == "publish":
                missing = [key for key in required if key not in obj]
                if missing:
                    raise ValueError("missing combined editorial metrics: " + ",".join(missing))
                for key in required:
                    obj[key] = max(0, min(100, int(float(obj.get(key, 0) or 0))))
            return obj

        result = self.gateway.run(
            prompt,
            validator=parse,
            max_output_tokens=260,
            timeout_seconds=25,
            allowed_providers=("gemini", "nvidia", "groq", "cloudflare"),
            purpose="editorial_selector",
        )
        fit = parse(result.text)
        raw_score = max(0, min(100, int(fit.get("fit_score", 0) or 0)))
        if commercial and fit["decision"] == "publish" and raw_score < 60:
            event("editorial", "normalized contradictory sold fit score", level=30, channel_id=channel.id, article_id=int(ed._v(article, "id", 0) or 0), raw_fit=raw_score, normalized_fit=60)
            raw_score = 60
        score = max(0, min(100, raw_score + int(learning.fit_adjustment)))
        if fit["decision"] == "reject":
            return ed.EditorialOutcome(Decision.REJECT, reason=ed._clean(fit.get("reason"), 600), fit_score=score, provider=result.provider, model=result.model)

        if commercial:
            value = dict(fit)
            value["reason"] = ed._clean(fit.get("reason"), 420)
            allowed, code, value_score = self._sold_value_allowed(value, score, ed._editorial_thresholds(channel))
            profile = "commercial"
            prefix = "SOLD_VALUE"
        else:
            value_keys = ("novelty", "consequence_or_insight", "mechanism", "reader_payoff", "retellability", "concrete_stakes", "why_now")
            value = {key: max(0, min(100, int(float(fit.get(key, 0) or 0)))) for key in value_keys}
            value["curiosity_only"] = bool(fit.get("curiosity_only", False))
            value["reason"] = ed._clean(fit.get("reason"), 420)
            allowed, code, value_score = self._value_allowed(value, score, ed._editorial_thresholds(channel))
            profile = "standard"
            prefix = "EDITORIAL_VALUE"
        event("ai", "RC102 fit/value combined", channel_id=channel.id, article_id=int(ed._v(article, "id", 0) or 0), profile=profile)
        if not allowed:
            return ed.EditorialOutcome(Decision.REJECT, reason=f"{prefix}_REJECT score={value_score}; code={code}; " + ed._clean(value.get("reason"), 420), fit_score=score, editorial_value_score=value_score, provider=result.provider, model=result.model)
        return ed.EditorialOutcome(Decision.PUBLISH, reason=f"{prefix}_PASS score={value_score}; lane={code}; fit={score}; learning={learning.fit_adjustment:+d}", angle=ed._clean(fit.get("angle"), 500), fit_score=score, editorial_value_score=value_score, provider=result.provider, model=result.model)

    ed.EditorialEngine._select_editorial = combined_select


def install_runtime_contracts() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _install_publisher_contract()
    _install_ui_contract()
    _install_recovery_contract()
    _install_supervisor_contract()
    _install_ai_efficiency_contract()
    _INSTALLED = True
