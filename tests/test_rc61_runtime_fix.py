from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path

from PIL import Image

from telegram_autopilot.database import Database, now_iso
from telegram_autopilot.models import CollectedArticle
from telegram_autopilot.rc33_policy import install_rc33_policy
from telegram_autopilot.rc53_hardening import install_rc53_hardening
from telegram_autopilot.rc61_runtime_fix import (
    _safe_photo_bytes,
    editorial_link_score,
    extract_page_published_at_rc61,
    install_rc61_runtime_fix,
)
from telegram_autopilot.media_pipeline import PreparedMedia


def test_editorial_link_ranking_rejects_directory_noise_and_keeps_real_stories():
    aotw = "https://www.adsoftheworld.com/"
    assert editorial_link_score(aotw, "https://www.adsoftheworld.com/agencies/the-reactor", "Agency: The Reactor") < 0
    assert editorial_link_score(aotw, "https://www.adsoftheworld.com/brands/foo", "Foo") < 0
    assert editorial_link_score(aotw, "https://www.adsoftheworld.com/campaigns/who-will-you-take", "Who will you take?") > 100

    shots = "https://shots.net/"
    assert editorial_link_score(shots, "https://shots.net/news/view/a-real-campaign-story", "A real campaign story worth reading") > 100

    lbb = "https://lbbonline.com/"
    assert editorial_link_score(lbb, "https://lbbonline.com/people/someone", "Someone Person") < 0
    assert editorial_link_score(lbb, "https://lbbonline.com/news/a-useful-creative-story", "A useful creative story with details") > 100


def test_textual_shots_byline_date_is_extracted_without_weakening_future_guard():
    html = """
    <html><body><article>
      <h1>Campaign story</h1>
      <p>by Jamie Madge on 1st September 2026</p>
      <p>Story body.</p>
    </article></body></html>
    """
    value = extract_page_published_at_rc61(html, "https://shots.net/news/view/campaign-story", previous=lambda *_: "")
    dt = datetime.fromisoformat(value)
    assert (dt.year, dt.month, dt.day) == (2026, 9, 1)
    assert dt.tzinfo is not None


def test_jsonld_single_quote_date_is_extracted():
    html = "<script type='application/ld+json'>{'datePublished':'2026-09-01T07:30:00Z'}</script>"
    value = extract_page_published_at_rc61(html, "https://example.com/news/item", previous=lambda *_: "")
    assert value.startswith("2026-09-01T07:30:00")


def test_non_jpeg_photo_is_normalized_to_telegram_safe_jpeg():
    buf = io.BytesIO()
    Image.new("RGB", (640, 360), (120, 80, 30)).save(buf, format="WEBP")
    item = PreparedMedia(index=1, kind="image", url="https://cdn.example/img?auto=format")
    item.data = buf.getvalue()
    item.mime_type = "image/webp"
    item.width = 640
    item.height = 360
    fixed = _safe_photo_bytes(item)
    assert fixed is item
    assert item.mime_type == "image/jpeg"
    assert item.data.startswith(b"\xff\xd8")
    assert item.width == 640 and item.height == 360
    assert len(item.digest) == 64


def test_pending_prefilter_skips_stale_high_priority_without_spending_return_slot(tmp_path: Path):
    install_rc33_policy()
    install_rc53_hardening()
    install_rc61_runtime_fix()
    db = Database(tmp_path / "rc61.sqlite3")
    cid = db.save_channel(
        channel_id=None, name="ПРОДАНО!", telegram_chat_id="@test_channel", editorial_profile="marketing",
        enabled=True, include_source_link=False, poll_interval_minutes=5, min_publish_interval_minutes=0,
        dedupe_window_hours=72, max_age_hours=24, max_posts_per_cycle=3,
    )
    stale_source = db.save_source(source_id=None, channel_id=cid, kind="rss", name="Old high", url="https://old.example/feed", enabled=True, priority=100)
    fresh_source = db.save_source(source_id=None, channel_id=cid, kind="rss", name="Fresh lower", url="https://fresh.example/feed", enabled=True, priority=50)
    stale = CollectedArticle("old", "Old campaign", "https://old.example/2026/08/20/old", "Old body " * 80, "2026-08-20T10:00:00+00:00", ["image|https://old.example/x.jpg"])
    fresh = CollectedArticle("fresh", "Fresh campaign", "https://fresh.example/2026/09/01/fresh", "Fresh body " * 80, now_iso(), ["image|https://fresh.example/x.jpg"])
    sources = {s.id: s for s in db.list_sources(cid)}
    old_id = db.insert_collected(sources[stale_source], stale, baseline=False)
    fresh_id = db.insert_collected(sources[fresh_source], fresh, baseline=False)
    rows = db.pending_articles(cid, limit=1)
    assert len(rows) == 1
    assert int(rows[0]["id"]) == int(fresh_id)
    assert db.get_article(int(old_id))["status"] == "rejected"
    assert "RC61 FRESHNESS PREFILTER" in str(db.get_article(int(old_id))["reject_reason"])
