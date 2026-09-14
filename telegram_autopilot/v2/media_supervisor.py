from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

from .production_supervisor import ProductionSupervisorService
from .supervisor import Incident, SupervisorConfig


class MediaAwareProductionSupervisorService(ProductionSupervisorService):
    """Expose media starvation instead of reporting an empty monitoring queue healthy."""

    def _channel_stats(self) -> dict[str, Any]:
        out = super()._channel_stats()
        cut60 = datetime.fromtimestamp(time.time() - 3600, tz=timezone.utc).astimezone().isoformat(timespec="seconds")
        with self.store.connect() as con:
            for cid, stats in out.items():
                channel_id = int(cid)
                stats["media_required_60m"] = int(
                    con.execute(
                        """SELECT COUNT(*) FROM articles
                           WHERE channel_id=? AND discovered_at>=?
                             AND last_error_code IN ('MEDIA_REQUIRED','MEDIA_REQUIRED_SKIPPED','TELEGRAM_MEDIA_REFRESH_REQUIRED')""",
                        (channel_id, cut60),
                    ).fetchone()[0]
                    or 0
                )
                raw = content = filtered = 0
                rows = con.execute(
                    "SELECT article_layout_json FROM articles WHERE channel_id=? AND discovered_at>=? ORDER BY id DESC LIMIT 300",
                    (channel_id, cut60),
                ).fetchall()
                for row in rows:
                    try:
                        layout = json.loads(str(row["article_layout_json"] or "{}"))
                        telegram = layout.get("telegram") if isinstance(layout, dict) else None
                        media_filter = telegram.get("media_filter") if isinstance(telegram, dict) else None
                        if not isinstance(media_filter, dict):
                            continue
                        filtered += 1
                        raw += int(media_filter.get("raw_candidates") or 0)
                        content += int(media_filter.get("content_media") or 0)
                    except Exception:
                        continue
                stats["telegram_filtered_articles_60m"] = filtered
                stats["telegram_raw_candidates_60m"] = raw
                stats["telegram_content_media_60m"] = content
        return out

    @staticmethod
    def _media_starved(stats: dict[str, Any]) -> bool:
        return bool(
            int(stats.get("media_required_60m") or 0) >= 3
            and int(stats.get("telegram_raw_candidates_60m") or 0) >= 3
            and int(stats.get("telegram_content_media_60m") or 0) == 0
            and int(stats.get("published_60m") or 0) == 0
        )

    def _operational_states(self, snapshot: dict[str, Any], cfg: SupervisorConfig) -> dict[str, dict[str, Any]]:
        result = super()._operational_states(snapshot, cfg)
        for cid, stats in dict(snapshot.get("channel_stats") or {}).items():
            if not self._media_starved(dict(stats or {})):
                continue
            state = result.setdefault(str(cid), {"state": "HEALTHY", "reasons": []})
            reasons = list(state.get("reasons") or [])
            reasons.append(
                f"media starvation: MEDIA_REQUIRED={int(stats.get('media_required_60m') or 0)}, "
                f"Telegram content_media=0/{int(stats.get('telegram_raw_candidates_60m') or 0)} candidates"
            )
            state["state"] = "DEGRADED"
            state["reasons"] = reasons
        return result

    def evaluate(self, snapshot: dict[str, Any], cfg: SupervisorConfig | None = None) -> list[Incident]:
        incidents = list(super().evaluate(snapshot, cfg))
        now = time.time()
        operational = bool(snapshot.get("expected_running") or snapshot.get("runtime_running"))
        for cid, stats_obj in dict(snapshot.get("channel_stats") or {}).items():
            stats = dict(stats_obj or {})
            code = f"MEDIA_STARVATION_{cid}"
            starved = bool(operational and self._media_starved(stats))
            elapsed = self._condition_elapsed(code, starved, now)
            if not starved or elapsed < 120:
                continue
            name = str(stats.get("name") or cid)
            incidents.append(
                Incident(
                    "WARNING",
                    code,
                    f"Канал «{name}» не отримує придатне медіа",
                    f"За 60 хв MEDIA_REQUIRED={int(stats.get('media_required_60m') or 0)}; "
                    f"Telegram candidates={int(stats.get('telegram_raw_candidates_60m') or 0)}; "
                    f"content_media={int(stats.get('telegram_content_media_60m') or 0)}; "
                    f"published/60m={int(stats.get('published_60m') or 0)}.",
                )
            )
        return incidents
