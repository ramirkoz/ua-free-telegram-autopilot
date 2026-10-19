"""2.2.3 media evidence core.

Regression for the operator cases that 2.2.1/2.2.2 did not fix:
* Tom's Hardware F-22 / Wi-Fi: schema.org Article.image listed ONE photo in
  16:9, 1:1 and 4:3 renditions; the extractor treated them as a gallery and
  the low-contrast photo (jet on clear sky) skipped pixel dedupe entirely.
* a site-wide promo carousel image "matched" the story through CSS class names.
* TrendHunter / commercial: CDN 403 looked like "filtered by media policy" and
  re-polling the same assets reset the READY media backoff within a minute.
"""
from __future__ import annotations

import json
from io import BytesIO
from types import SimpleNamespace

from PIL import Image, ImageDraw, ImageOps

from telegram_autopilot import media_pipeline
from telegram_autopilot.article_extractor import extract_article_content
from telegram_autopilot.media import canonical_asset_key
from telegram_autopilot.v2.crop_dedupe import same_cropped_image
from telegram_autopilot.v2.domain import BlockedBy, Decision, Stage
from telegram_autopilot.v2.ready_backlog import ReadyBacklogStore
from telegram_autopilot.v2.storage import now_iso
from telegram_autopilot.v2.visual_media_dedupe import remove_visual_duplicates


# --------------------------------------------------------------------------- assets

def test_canonical_asset_key_groups_renditions_only():
    same = [
        ("https://cdn.example.net/L7BkiwxuV26xQsmk9K7L5C-1920-80.jpg",
         "https://cdn.example.net/v2/t:0,l:420,cw:1080,ch:1080,q:80,w:1080/L7BkiwxuV26xQsmk9K7L5C.jpg"),
        ("https://cdn.example.net/L7BkiwxuV26xQsmk9K7L5C-1600-80.jpg.webp",
         "https://cdn.example.net/L7BkiwxuV26xQsmk9K7L5C.jpg"),
        ("https://site.test/wp-content/uploads/2026/10/photo-1200x675.jpg",
         "https://site.test/wp-content/uploads/2026/10/photo.jpg"),
        ("https://img.test/image/upload/w_800,c_fill,q_auto/v1/a/hero.jpg",
         "https://img.test/image/upload/w_400/v1/a/hero.jpg"),
    ]
    different = [
        ("https://cdn.example.net/L7BkiwxuV26xQsmk9K7L5C-1920-80.jpg",
         "https://cdn.example.net/kfvNwDT4D6jpoBvqVwPdcE-1920-80.jpg"),
        ("https://site.test/2026/09/photo.jpg", "https://site.test/2026/10/photo.jpg"),
        ("https://site.test/img/img_1001.jpg", "https://site.test/img/img_1002.jpg"),
        ("https://cdn.test/thumbs/644586_1_1200.jpeg", "https://cdn.test/thumbs/644586_2_1200.jpeg"),
    ]
    for a, b in same:
        assert canonical_asset_key(a) == canonical_asset_key(b), (a, b)
    for a, b in different:
        assert canonical_asset_key(a) != canonical_asset_key(b), (a, b)


def _article_html(images: list[str]) -> str:
    schema = {
        "@context": "https://schema.org", "@type": "NewsArticle",
        "headline": "Raptor pilot commands wingman drone",
        "mainEntityOfPage": "https://news.test/drones/raptor-wingman",
        "image": [{"@type": "ImageObject", "url": url} for url in images],
    }
    return f"""<html><head><title>Raptor pilot commands wingman drone</title>
    <script type="application/ld+json">{json.dumps(schema)}</script></head><body>
    <article><h1>Raptor pilot commands wingman drone</h1>
    <p>A Raptor pilot commanded a wingman drone in a simulated combat test over the range.</p>
    <p>The Air Force says the program integrates uncrewed aircraft into fighter squadrons.</p></article>
    </body></html>"""


def test_jsonld_aspect_ratio_renditions_are_one_asset_not_a_gallery():
    html = _article_html([
        "https://cdn.example.net/L7BkiwxuV26xQsmk9K7L5C-1920-80.jpg",
        "https://cdn.example.net/v2/t:0,l:420,cw:1080,ch:1080,q:80,w:1080/L7BkiwxuV26xQsmk9K7L5C.jpg",
        "https://cdn.example.net/v2/t:0,l:240,cw:1440,ch:1080,q:80,w:1440/L7BkiwxuV26xQsmk9K7L5C.jpg",
        "https://cdn.example.net/v2/t:0,l:0,cw:1920,ch:1080,q:80,w:1920/L7BkiwxuV26xQsmk9K7L5C.jpg",
    ])
    layout = json.loads(extract_article_content(html, "https://news.test/drones/raptor-wingman").layout_json)
    media = [b for b in layout["blocks"] if b.get("type") == "media"]
    assert len(media) == 1
    assert media[0]["gallery"] is False
    assert canonical_asset_key(media[0]["url"]) in layout["page_image_assets"]


def test_jsonld_distinct_assets_remain_a_gallery():
    html = _article_html([
        "https://cdn.example.net/AaaaaaaaaaaaaaaaaaaaA1-1920-80.jpg",
        "https://cdn.example.net/BbbbbbbbbbbbbbbbbbbbB2-1920-80.jpg",
        "https://cdn.example.net/CccccccccccccccccccccC3-1920-80.jpg",
    ])
    layout = json.loads(extract_article_content(html, "https://news.test/drones/raptor-wingman").layout_json)
    media = [b for b in layout["blocks"] if b.get("type") == "media"]
    assert len(media) == 3
    assert all(b["gallery"] for b in media)


# --------------------------------------------------------------------------- pixels

def _jpeg(image: Image.Image, quality: int = 85) -> bytes:
    buf = BytesIO()
    image.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def _sky(plane_at=(880, 150), flares=((640, 360), (995, 610))) -> Image.Image:
    """Low-contrast scene like the F-22 hero: clear sky, one small jet, two flares."""
    im = Image.new("RGB", (1920, 1080), (52, 112, 205))
    draw = ImageDraw.Draw(im)
    x, y = plane_at
    draw.polygon([(x + 80, y), (x + 120, y + 120), (x + 220, y + 210), (x + 140, y + 230),
                  (x + 80, y + 280), (x + 20, y + 230), (x - 60, y + 210), (x + 40, y + 120)], fill=(205, 208, 212))
    for fx, fy in flares:
        draw.ellipse((fx - 9, fy - 9, fx + 9, fy + 9), fill=(255, 236, 190))
        draw.line((fx, fy, fx + 40, fy + 420), fill=(232, 236, 242), width=8)
    return im


def _renditions(im: Image.Image) -> list[bytes]:
    hero = _jpeg(im, 82)
    square = _jpeg(im.crop((420, 0, 1500, 1080)), 80)
    classic = _jpeg(im.crop((240, 0, 1680, 1080)), 80)
    return [hero, square, classic]


def test_low_contrast_responsive_renditions_reduce_to_one():
    items = [SimpleNamespace(kind="image", data=data) for data in _renditions(_sky())]
    remaining, removed = remove_visual_duplicates(items)
    assert removed == 2
    assert len(remaining) == 1
    with Image.open(BytesIO(remaining[0].data)) as kept:
        assert kept.size == (1920, 1080)       # highest resolution survives


def test_same_sky_different_frames_are_not_merged():
    base = _jpeg(_sky(), 85)
    moved = _jpeg(_sky(plane_at=(300, 520)), 85)
    erased = Image.new("RGB", (1920, 1080), (52, 112, 205))
    mirrored = _jpeg(ImageOps.mirror(_sky()), 85)
    assert not same_cropped_image(base, moved)
    assert not same_cropped_image(base, _jpeg(erased, 85))
    assert not same_cropped_image(base, mirrored)
    items = [SimpleNamespace(kind="image", data=d) for d in (base, moved, mirrored)]
    remaining, removed = remove_visual_duplicates(items)
    assert removed == 0 and len(remaining) == 3


def test_video_is_never_collapsed_with_its_poster():
    poster = _jpeg(_sky(), 85)
    items = [SimpleNamespace(kind="image", data=poster), SimpleNamespace(kind="video", data=poster)]
    remaining, removed = remove_visual_duplicates(items)
    assert removed == 0 and len(remaining) == 2


# --------------------------------------------------------------------------- selection

def _fake_probe(item, *, marketing_context=False):
    item.mime_type = "image/jpeg"
    item.width, item.height = 1200, 800
    item.digest = f"digest-{item.url}"
    item.data = b"image"
    return item


def test_css_class_context_is_not_story_evidence(monkeypatch):
    monkeypatch.setattr(media_pipeline, "_probe_image", _fake_probe)
    layout = json.dumps({"blocks": [{
        "type": "media", "index": 1, "kind": "image", "position": 0.0, "alt": "", "caption": "",
        "url": "https://cdn.example.net/flexiimages/uq175ysqvs1775547791-400-80.jpeg",
        "context": "news-page widget membership-slider premium raptor wingman drone combat",
    }]})
    prepared = media_pipeline.prepare_article_media(
        layout, [], title="Raptor pilot commands wingman drone in combat",
        article_text="A Raptor pilot commanded a wingman drone in simulated combat.",
    )
    assert prepared.body == []
    assert prepared.drop_reasons.get("not_story_media") == 1


def test_page_declared_lead_image_is_story_media(monkeypatch):
    monkeypatch.setattr(media_pipeline, "_probe_image", _fake_probe)
    url = "https://platform.example.com/uploads/chorus_asset/file/25544255/2162439650.jpg?quality=90"
    layout = json.dumps({
        "page_image_assets": [canonical_asset_key("https://platform.example.com/uploads/chorus_asset/file/25544255/2162439650.jpg")],
        "blocks": [{"type": "media", "index": 1, "kind": "image", "position": 0.25,
                    "alt": "Capitol Hill", "caption": "", "url": url, "context": "duet--article--lede"}],
    })
    prepared = media_pipeline.prepare_article_media(
        layout, [], title="Video game ownership bill introduced in Congress",
        article_text="A new bill would protect digital game purchases.",
    )
    assert [m.url for m in prepared.body] == [url]


def test_commercial_gallery_relaxation_excludes_cards_for_other_stories(monkeypatch):
    monkeypatch.setattr(media_pipeline, "_probe_image", _fake_probe)
    blocks = [
        {"type": "media", "index": 1, "kind": "image", "position": 0.0, "gallery": True,
         "alt": "", "url": "https://cdn.example.com/hero-1.jpg", "context": "visual-shell"},
        {"type": "media", "index": 2, "kind": "image", "position": 1.0, "gallery": True,
         "alt": "Top 90 Interactive Trends in September", "url": "https://cdn.example.com/top90.jpg",
         "context": "visual-shell"},
        {"type": "media", "index": 3, "kind": "image", "position": 0.9, "gallery": True,
         "alt": "", "url": "https://cdn.example.com/rail.jpg", "context": "related-trends rail"},
    ]
    prepared = media_pipeline.prepare_article_media(
        json.dumps({"blocks": blocks}), [], title="Character-Themed Racing Fan Zones",
        article_text="Sanrio brings Hello Kitty back to the racing finale fan zone.", marketing_context=True,
    )
    assert [m.url for m in prepared.body] == ["https://cdn.example.com/hero-1.jpg"]


def test_cdn_block_is_reported_as_http_403_not_as_bad_media(monkeypatch):
    class Blocked:
        status = 403
        headers = {"content-type": "text/html"}
        body = b"<!doctype html>Access denied"

    monkeypatch.setattr(media_pipeline, "fetch_url", lambda *a, **k: Blocked())
    layout = json.dumps({"blocks": [
        {"type": "media", "index": i, "kind": "image", "position": 0.0, "gallery": True, "alt": "",
         "url": f"https://cdn.example.com/campaign_{i}_1200.jpeg", "context": "visual-shell"}
        for i in range(1, 4)
    ]})
    prepared = media_pipeline.prepare_article_media(layout, [], title="Campaign", article_text="Campaign", marketing_context=True)
    assert prepared.body == []
    assert prepared.drop_reasons == {"http_403": 3}


# --------------------------------------------------------------------------- READY recovery

def _seed_blocked_ready(store: ReadyBacklogStore, media: list[str], tried: list[str]) -> None:
    stamp = now_iso()
    layout = {"media_recovery": {"attempts": 1, "classification": "recoverable", "tried_assets": tried}}
    with store.connect() as con:
        con.execute("INSERT INTO channels(id,name,telegram_chat_id,enabled,max_age_hours,created_at,updated_at) VALUES(1,'c','',1,24,?,?)", (stamp, stamp))
        con.execute("INSERT INTO sources(id,channel_id,kind,name,url,enabled,initialized,priority) VALUES(1,1,'rss','s','https://example.com/feed',1,1,100)")
        con.execute(
            """INSERT INTO articles(id,channel_id,source_id,external_id,title,source_url,canonical_source_url,raw_text,
                   source_published_at,discovered_at,stage,decision,blocked_by,ready_at,media_json,article_layout_json,
                   last_error_code,next_retry_at)
               VALUES(1,1,1,'item-1','Campaign','https://example.com/a','https://example.com/a','body',?,?,?,?,?,?,?,?,?,?)""",
            (stamp, stamp, str(Stage.READY), str(Decision.PUBLISH), str(BlockedBy.MEDIA), stamp,
             json.dumps(media), json.dumps(layout), "MEDIA_REQUIRED", "2099-01-01T00:00:00+00:00"),
        )


def _recollect(store: ReadyBacklogStore, media: list[str]) -> None:
    store.insert_collected(
        channel_id=1, source_id=1, external_id="item-1", title="Campaign", source_url="https://example.com/a",
        raw_text="body", media_json=json.dumps(media), article_layout_json=json.dumps({"blocks": []}),
    )


def test_repoll_of_already_tried_assets_keeps_media_backoff(tmp_path):
    store = ReadyBacklogStore(tmp_path / "v2.sqlite3")
    media = [f"https://cdn.example.com/p/644586_{i}_1200.jpeg" for i in (1, 2)]
    _seed_blocked_ready(store, media, sorted(canonical_asset_key(u) for u in media))
    # Same assets again, different renditions/order: not fresh media.
    _recollect(store, [f"https://cdn.example.com/p/644586_{i}_1200.jpeg?imwidth=600" for i in (2, 1)])
    row = store.get_article(1)
    assert str(row["blocked_by"]) == str(BlockedBy.MEDIA)
    assert str(row["next_retry_at"]).startswith("2099")
    assert json.loads(row["article_layout_json"])["media_recovery"]["attempts"] == 1


def test_genuinely_new_asset_unblocks_ready(tmp_path):
    store = ReadyBacklogStore(tmp_path / "v2.sqlite3")
    media = ["https://cdn.example.com/p/644586_1_1200.jpeg"]
    _seed_blocked_ready(store, media, [canonical_asset_key(media[0])])
    _recollect(store, media + ["https://cdn.example.com/p/644586_3_1200.jpeg"])
    row = store.get_article(1)
    assert str(row["blocked_by"]) == str(BlockedBy.NONE)
    assert str(row["next_retry_at"]) == ""


# --------------------------------------------------------------------------- 2.2.3 completion

def test_burst_of_same_scene_frames_has_no_false_merges():
    """45 pairs of different frames of one low-contrast scene (negative corpus)."""
    frames = [_jpeg(_sky(plane_at=(300 + 120 * k, 150 + 40 * k)), 85) for k in range(10)]
    remaining, removed = remove_visual_duplicates([SimpleNamespace(kind="image", data=d) for d in frames])
    assert removed == 0 and len(remaining) == 10


def test_svg_icons_are_not_media_or_gallery_items():
    html = """<html><head><title>Raptor pilot commands wingman drone</title></head><body>
    <div class="membership-slider">
      <img src="https://cdn.example.net/flexiimages/2lfo9jmvho1765179166.svg" alt="Badge picture">
      <img src="https://cdn.example.net/flexiimages/os9yhxfeal1776177053.svg" alt="Latest on CPUs">
    </div>
    <article><h1>Raptor pilot commands wingman drone</h1>
    <figure><img src="https://cdn.example.net/hero-image-1200x675.jpg" width="1200" height="675" alt="Raptor"></figure>
    <p>A Raptor pilot commanded a wingman drone in a simulated combat test.</p></article></body></html>"""
    layout = json.loads(extract_article_content(html, "https://news.test/drones/raptor").layout_json)
    urls = [b["url"] for b in layout["blocks"] if b.get("type") == "media"]
    assert not any(u.endswith(".svg") for u in urls)


def test_pre_223_media_permanent_items_get_one_fresh_recovery(tmp_path):
    store = ReadyBacklogStore(tmp_path / "v2.sqlite3")
    _seed_blocked_ready(store, ["https://cdn.example.com/p/a_1.jpeg"], ["cdn.example.com/p/a_1"])
    with store.connect() as con:
        con.execute("""UPDATE articles SET stage='ARCHIVED',decision='REJECT',final_text='Готовий текст',
                       last_error_code='MEDIA_REQUIRED_PERMANENT',next_retry_at='' WHERE id=1""")
        con.commit()
    first = store._restore_223_media_permanent_once()
    second = store._restore_223_media_permanent_once()
    row = store.get_article(1)
    assert first == {"skipped": 0, "restored": 1}
    assert second["skipped"] == 1
    assert str(row["stage"]) == str(Stage.READY) and str(row["decision"]) == str(Decision.PUBLISH)
    assert str(row["last_error_code"]) == "MEDIA_REQUIRED"
    assert json.loads(row["article_layout_json"])["media_recovery"]["attempts"] == 0


def test_media_prepared_event_carries_replayable_trace():
    import inspect
    from telegram_autopilot.v2.publisher import Publisher
    source = inspect.getsource(Publisher)
    assert "media_trace=media_trace" in source
    assert '"sha256"' in source and '"kept"' in source


def test_blocked_sources_are_disabled_once_and_their_items_stay_archived(tmp_path):
    from telegram_autopilot.v2.source_retirement import retire_blocked_sources_once
    store = ReadyBacklogStore(tmp_path / "v2.sqlite3")
    _seed_blocked_ready(store, ["https://cdn.example.com/p/a_1.jpeg"], [])
    with store.connect() as con:
        con.execute("UPDATE sources SET name='Trend Hunter',url='https://www.trendhunter.com/rss' WHERE id=1")
        con.execute("INSERT INTO sources(id,channel_id,kind,name,url,enabled,initialized,priority) VALUES(2,1,'rss','Campaign','https://feeds.example.org/campaign',1,1,100)")
        con.execute("INSERT INTO source_health(source_id,last_outcome,consecutive_failures) VALUES(2,'HTTP_403',12)")
        con.execute("INSERT INTO sources(id,channel_id,kind,name,url,enabled,initialized,priority) VALUES(3,1,'rss','Fast Company','https://www.fastcompany.com/feed',1,1,100)")
        con.execute("""UPDATE articles SET stage='ARCHIVED',decision='REJECT',final_text='Текст',
                       last_error_code='MEDIA_REQUIRED_PERMANENT' WHERE id=1""")
        con.commit()
    first = retire_blocked_sources_once(store)
    assert sorted(first["retired"]) == ["Campaign (channel 1)", "Trend Hunter (channel 1)"]
    assert retire_blocked_sources_once(store)["skipped"] == 1
    with store.connect() as con:
        enabled = {int(r["id"]): int(r["enabled"]) for r in con.execute("SELECT id,enabled FROM sources")}
    assert enabled == {1: 0, 2: 0, 3: 1}
    # The archived TrendHunter item is not resurrected by the 2.2.3 restore.
    assert store._restore_223_media_permanent_once()["restored"] == 0
