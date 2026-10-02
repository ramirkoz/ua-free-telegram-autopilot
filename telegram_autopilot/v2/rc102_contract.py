from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from . import editorial as editorial_mod
from .ai_gateway import AIGateway
from .domain import Decision, Stage
from .editorial import EditorialEngine, EditorialOutcome
from .editorial_review import EditorialReviewService, ReviewItem
from .loghub import event
from .publisher import Publisher
from .ready_backlog import ReadyBacklogSupervisor
from .supervisor import Incident

_human_publish_ctx = threading.local()
_original_prepublish_quality_issues = editorial_mod.prepublish_quality_issues


def _rc102_prepublish_quality_issues(channel, article, text):
    if bool(getattr(_human_publish_ctx, "active", False)):
        return ()
    return _original_prepublish_quality_issues(channel, article, text)


editorial_mod.prepublish_quality_issues = _rc102_prepublish_quality_issues


class Rc102EditorialReviewService(EditorialReviewService):
    """Human approval remains visible until actual publication; reject is terminal."""

    def candidates(self, *, limit: int = 250) -> list[ReviewItem]:
        self.ensure_schema()
        with self.store.connect() as con:
            rows = con.execute(
                """
                SELECT a.id,a.channel_id,c.name channel_name,a.title,a.stage,a.blocked_by,
                       COALESCE(NULLIF(a.last_error_detail,''),NULLIF(a.status_detail,''),NULLIF(a.reject_reason,''),'') reason,
                       a.final_text,s.name source_name,a.discovered_at
                FROM articles a
                JOIN channels c ON c.id=a.channel_id
                JOIN sources s ON s.id=a.source_id
                WHERE TRIM(COALESCE(a.final_text,''))<>''
                  AND a.stage<>'PUBLISHED'
                  AND NOT EXISTS (
                      SELECT 1 FROM editorial_actions ea
                      WHERE ea.article_id=a.id
                        AND ea.id=(SELECT MAX(ea2.id) FROM editorial_actions ea2 WHERE ea2.article_id=a.id)
                        AND ea.action='reject'
                  )
                ORDER BY datetime(a.discovered_at) DESC,a.id DESC LIMIT ?
                """,
                (max(1, min(1000, int(limit))),),
            ).fetchall()
        return [
            ReviewItem(
                int(r["id"]), int(r["channel_id"]), str(r["channel_name"]), str(r["title"] or ""),
                str(r["stage"] or ""), str(r["blocked_by"] or ""), str(r["reason"] or ""),
                str(r["final_text"] or ""), str(r["source_name"] or ""), str(r["discovered_at"] or ""),
            )
            for r in rows
        ]

    def approve(self, article_id: int) -> None:
        super().approve(article_id)
        row = self.store.get_article(int(article_id))
        if row is not None:
            self.store.update_article(int(article_id), status_detail="Погоджено редактором: очікує фактичної публікації")
            event("editorial", "HUMAN_APPROVE", channel_id=int(row["channel_id"]), article_id=int(article_id))

    def edit(self, article_id: int, text: str) -> None:
        super().edit(article_id, text)
        row = self.store.get_article(int(article_id))
        if row is not None:
            self.store.update_article(int(article_id), status_detail="Відредаговано й погоджено редактором: очікує фактичної публікації")
            event("editorial", "HUMAN_APPROVE", channel_id=int(row["channel_id"]), article_id=int(article_id), edited=True)

    def reject(self, article_id: int, reason: str = "Відхилено редактором вручну") -> None:
        super().reject(article_id, reason)
        row = self.store.get_article(int(article_id))
        if row is None or str(row["stage"]) != str(Stage.ARCHIVED) or str(row["decision"]) != str(Decision.REJECT):
            raise RuntimeError("HUMAN_REJECT_NOT_DURABLE")
        event("editorial", "HUMAN_REJECT", channel_id=int(row["channel_id"]), article_id=int(article_id))

    def record_publish_now(self, article_id: int, result: str) -> None:
        super().record_publish_now(article_id, result)
        row = self.store.get_article(int(article_id))
        if row is None:
            return
        event(
            "editorial",
            "HUMAN_PUBLISH_SUCCESS" if result == "PUBLISHED" else "HUMAN_PUBLISH_BLOCKED",
            level=20 if result == "PUBLISHED" else 30,
            channel_id=int(row["channel_id"]), article_id=int(article_id), result=str(result),
        )


class Rc102Publisher(Publisher):
    """Human approval bypasses repeated editorial/schedule gates, not delivery safety."""

    def can_publish_now(self, channel_id: int) -> tuple[bool, str]:
        if bool(getattr(_human_publish_ctx, "active", False)):
            return True, "HUMAN_OVERRIDE"
        return super().can_publish_now(channel_id)

    def publish_human_approved(self, article_id: int) -> str:
        row = self.store.get_article(int(article_id))
        if row is None:
            raise KeyError(article_id)
        event("editorial", "HUMAN_PUBLISH_REQUEST", channel_id=int(row["channel_id"]), article_id=int(article_id))
        previous = bool(getattr(_human_publish_ctx, "active", False))
        _human_publish_ctx.active = True
        try:
            return super().publish_one(int(article_id))
        finally:
            _human_publish_ctx.active = previous


class Rc102Gateway(AIGateway):
    """Bound provider fan-out by task purpose instead of walking every route."""

    def run(self, prompt: str, **kwargs):
        purpose = str(kwargs.get("purpose") or "content")
        if kwargs.get("allowed_providers") is None:
            if purpose in {"monitoring_selector", "editorial_selector", "value_gate", "commercial_value_gate"}:
                kwargs["allowed_providers"] = ("gemini", "nvidia")
            elif purpose in {"writer", "final_editor"}:
                kwargs["allowed_providers"] = ("gemini", "nvidia", "groq")
        return super().run(prompt, **kwargs)


class Rc102EditorialEngine(EditorialEngine):
    """One AI selection call returns both channel fit and editorial value."""

    def _select_editorial(self, channel, article: Any) -> EditorialOutcome:
        p = channel.policy
        learning = self.learning.topic_assessment(channel.id, article)
        if learning.hard_suppress:
            reason = f"LEARNING_ADMIN_DISLIKE: very close recent editor-disliked story #{learning.matched_article_id}; similarity={learning.matched_similarity:.2f}"
            event("learning", "topic hard suppress", channel_id=channel.id, article_id=int(editorial_mod._v(article, "id", 0) or 0), detail=reason)
            return EditorialOutcome(Decision.REJECT, reason=reason, fit_score=0)

        topic_memory = self.learning.topic_memory_block(channel.id, article)
        commercial = editorial_mod._is_commercial_editorial(channel)
        value_schema = (
            '"commercial_mechanism":0,"consumer_behavior":0,"creative_execution":0,"measurable_result":0,"strategic_transferability":0,"why_now":0,"general_interest":0,"retellability":0,"culture_signal":0,"surprise_or_conflict":0,"consumer_relevance":0'
            if commercial else
            '"novelty":0,"consequence_or_insight":0,"mechanism":0,"reader_payoff":0,"retellability":0,"concrete_stakes":0,"why_now":0,"curiosity_only":false'
        )
        prompt = f"""Ти CHANNEL-FIT + EDITORIAL VALUE GATE Telegram-автопілота. Зроби ОДНЕ рішення замість двох AI-викликів.
PURPOSE: {p.purpose}
AUDIENCE: {p.audience}
SELECTION: {p.selection_rules}
EXCLUSIONS: {p.rejection_rules}
EXTRA: {p.selector_extra_prompt}
{topic_memory}
SOURCE NAME: {editorial_mod._clean(editorial_mod._v(article, 'source_name', ''), 300)}
SOURCE TITLE: {editorial_mod._clean(editorial_mod._v(article, 'title', ''), 700)}
SOURCE:
{editorial_mod._source_pack(article, 3600)}
Поверни ТІЛЬКИ JSON: {{"decision":"publish" або "reject","fit_score":0,"reason":"коротко","angle":"кут","topic_tags":["..."],{value_schema}}}"""

        required = (
            ("commercial_mechanism", "consumer_behavior", "creative_execution", "measurable_result", "strategic_transferability", "why_now", "general_interest", "retellability", "culture_signal", "surprise_or_conflict", "consumer_relevance")
            if commercial else
            ("novelty", "consequence_or_insight", "mechanism", "reader_payoff", "retellability", "concrete_stakes", "why_now")
        )

        def parse(raw: str):
            obj = editorial_mod._parse_json(raw)
            decision = str(obj.get("decision") or "").casefold()
            if decision not in {"publish", "reject"}:
                raise ValueError("invalid decision")
            for key in required:
                if key not in obj:
                    raise ValueError(f"missing score: {key}")
                obj[key] = max(0, min(100, int(float(obj.get(key, 0) or 0))))
            return obj

        result = self.gateway.run(prompt, validator=parse, max_output_tokens=320, timeout_seconds=25, purpose="editorial_selector")
        fit = parse(result.text)
        raw_score = max(0, min(100, int(fit.get("fit_score", 0) or 0)))
        if commercial and fit["decision"] == "publish" and raw_score < 60:
            raw_score = 60
        score = max(0, min(100, raw_score + int(learning.fit_adjustment)))
        if fit["decision"] == "reject":
            return EditorialOutcome(Decision.REJECT, reason=editorial_mod._clean(fit.get("reason"), 600), fit_score=score, provider=result.provider, model=result.model)

        thresholds = editorial_mod._editorial_thresholds(channel)
        value = {key: fit[key] for key in required}
        value["reason"] = editorial_mod._clean(fit.get("reason"), 420)
        if commercial:
            allowed, code, value_score = self._sold_value_allowed(value, score, thresholds)
            prefix = "SOLD_VALUE"
        else:
            value["curiosity_only"] = bool(fit.get("curiosity_only", False))
            allowed, code, value_score = self._value_allowed(value, score, thresholds)
            prefix = "EDITORIAL_VALUE"
        event("ai", "selector/value combined", channel_id=channel.id, article_id=int(editorial_mod._v(article, "id", 0) or 0), profile="commercial" if commercial else "standard")
        if not allowed:
            return EditorialOutcome(Decision.REJECT, reason=f"{prefix}_REJECT score={value_score}; code={code}; " + editorial_mod._clean(fit.get("reason"), 420), fit_score=score, editorial_value_score=value_score, provider=result.provider, model=result.model)
        return EditorialOutcome(Decision.PUBLISH, reason=f"{prefix}_PASS score={value_score}; lane={code}; fit={score}; learning={learning.fit_adjustment:+d}", angle=editorial_mod._clean(fit.get("angle"), 500), fit_score=score, editorial_value_score=value_score, provider=result.provider, model=result.model)


class Rc102Supervisor(ReadyBacklogSupervisor):
    """Expose human-approved-but-unpublished work as an explicit incident."""

    def evaluate(self, snapshot: dict[str, Any], cfg=None):
        incidents = list(super().evaluate(snapshot, cfg))
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=5)).astimezone().isoformat(timespec="seconds")
        with self.store.connect() as con:
            rows = con.execute(
                """SELECT a.channel_id,c.name,COUNT(*) n,MIN(ea.created_at) oldest
                   FROM articles a
                   JOIN channels c ON c.id=a.channel_id
                   JOIN editorial_actions ea ON ea.article_id=a.id
                   WHERE a.stage<>'PUBLISHED'
                     AND ea.id=(SELECT MAX(ea2.id) FROM editorial_actions ea2 WHERE ea2.article_id=a.id)
                     AND ea.action IN ('approve','edit','publish_attempt')
                     AND datetime(ea.created_at)<=datetime(?)
                   GROUP BY a.channel_id,c.name""",
                (cutoff,),
            ).fetchall()
        for row in rows:
            incidents.append(Incident(
                "WARNING",
                f"APPROVED_NOT_PUBLISHED_{int(row['channel_id'])}",
                f"Погоджені матеріали каналу «{row['name']}» не дійшли до публікації",
                f"pending={int(row['n'] or 0)}; oldest_approval={str(row['oldest'] or '')}.",
            ))
        return incidents
