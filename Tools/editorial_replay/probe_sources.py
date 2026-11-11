"""Probe RSS sources with the project's own collector (read-only network fetch).

Usage: python probe_sources.py <repo> <out.json> name=url [name=url ...]
Reports HTTP/parse outcome, items, items with a verifiable timestamp, items in
the last 24/72 h, body length after extraction and media presence. HTTP 200 is
not treated as success: a usable source must return dated, recent items with text.
"""
import json, sys, time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

repo, out = sys.argv[1:3]
sys.path.insert(0, repo)
from telegram_autopilot.collector import collect_source  # noqa: E402
from telegram_autopilot.models import Source  # noqa: E402


def when(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        d = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            d = parsedate_to_datetime(raw)
        except Exception:
            return None
    return d.astimezone(timezone.utc) if d.tzinfo else None


now = datetime.now(timezone.utc)
report = []
for i, pair in enumerate(sys.argv[3:], start=1):
    name, url = pair.split("=", 1)
    rec = {"name": name, "url": url}
    started = time.time()
    src = Source(id=9000 + i, channel_id=2, kind="rss", name=name, url=url, enabled=True,
                 initialized=True, last_checked_at="", last_error="")
    try:
        items = collect_source(src)
        dates = [when(getattr(it, "published_at", "")) for it in items]
        dated = [d for d in dates if d]
        body = sorted(len(str(getattr(it, "raw_text", "") or "")) for it in items)
        rec.update(
            ok=True, items=len(items), dated=len(dated),
            last24=sum(1 for d in dated if now - d <= timedelta(hours=24)),
            last72=sum(1 for d in dated if now - d <= timedelta(hours=72)),
            median_body=body[len(body) // 2] if body else 0,
            short_body=sum(1 for b in body if b < 300),
            with_media=sum(1 for it in items if getattr(it, "media_urls", None)),
            newest=max(dated).isoformat(timespec="minutes") if dated else "",
            sample=[str(getattr(it, "title", ""))[:70] for it in items[:3]],
        )
    except Exception as exc:
        rec.update(ok=False, error=f"{type(exc).__name__}: {exc}"[:160])
    rec["seconds"] = round(time.time() - started, 1)
    report.append(rec)
    print(json.dumps(rec, ensure_ascii=False)[:420], flush=True)
json.dump(report, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
