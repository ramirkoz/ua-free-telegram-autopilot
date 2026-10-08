from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import telegram_autopilot.media_pipeline as legacy_media_pipeline
from telegram_autopilot.article_extractor import extract_article_content
from telegram_autopilot.media_pipeline import PreparedMedia
from telegram_autopilot.v2.domain import ChannelMode, EditorialRuntimeProfile
from telegram_autopilot.v2.media_pipeline import build_publication_media_bundle
from telegram_autopilot.v2.storage import V2Store, now_iso


def _seed_channel_source(store: V2Store, *, kind: str="page") -> int:
    stamp=now_iso()
    with store.connect() as con:
        con.execute(
            """INSERT INTO channels(
                 id,name,telegram_chat_id,enabled,channel_mode,editorial_runtime_profile,
                 created_at,updated_at
               ) VALUES(1,'T','@t',1,'editorial','commercial_editorial',?,?)""",
            (stamp,stamp),
        )
        return int(con.execute(
            "INSERT INTO sources(channel_id,kind,name,url,enabled,priority) VALUES(1,?,'S','https://example.com',1,100)",
            (kind,),
        ).lastrowid)


def test_rc112_gallery_outside_article_and_youtube_embed_are_preserved() -> None:
    html = """
    <html><head><title>Banana Gym Pass campaign</title></head><body>
      <article><p>Australian Bananas launched a gym pass campaign with Thinkerbell.</p></article>
      <section class="campaign-gallery view-gallery">
        <img src="https://cdn.example.com/banana-1.jpg" width="1200" height="800" alt="Banana Gym Pass"/>
        <img data-src="https://cdn.example.com/banana-2.jpg" width="1200" height="800" alt="Bring a banana"/>
        <iframe src="https://www.youtube.com/embed/AbCdEf12345" title="Campaign video"></iframe>
      </section>
    </body></html>
    """
    out=extract_article_content(html,"https://example.com/banana")
    layout=json.loads(out.layout_json)
    media=[b for b in layout["blocks"] if b.get("type")=="media"]
    urls=[str(b.get("url") or "") for b in media]
    assert "https://cdn.example.com/banana-1.jpg" in urls
    assert "https://cdn.example.com/banana-2.jpg" in urls
    assert "https://www.youtube.com/embed/AbCdEf12345" in urls
    assert sum(1 for b in media if b.get("gallery")) >= 2
    assert any(str(x).startswith("iframe|https://www.youtube.com/embed/AbCdEf12345") for x in out.media_urls)


def test_rc112_jsonld_article_image_list_is_kept() -> None:
    html = """
    <html><head><title>Wing delivery drones at Walmart</title>
    <script type="application/ld+json">
    {"@context":"https://schema.org","@type":"Article",
     "headline":"Wing delivery drones at Walmart",
     "url":"https://example.com/wing",
     "image":[
       "https://cdn.example.com/wing-1.jpg",
       "https://cdn.example.com/wing-2.jpg",
       "https://cdn.example.com/wing-3.jpg"
     ]}
    </script></head>
    <body><article><p>Wing expanded drone delivery for Walmart shoppers.</p></article></body></html>
    """
    out=extract_article_content(html,"https://example.com/wing")
    assert "https://cdn.example.com/wing-1.jpg" in out.media_urls
    assert "https://cdn.example.com/wing-2.jpg" in out.media_urls
    assert "https://cdn.example.com/wing-3.jpg" in out.media_urls


def test_rc112_publication_bundle_keeps_all_validated_gallery_media(monkeypatch) -> None:
    prepared=SimpleNamespace(
        featured=PreparedMedia(0,"image","https://cdn.example.com/hero.jpg",data=b"x",relevance_score=80),
        body=[
            PreparedMedia(1,"image","https://cdn.example.com/one.jpg",data=b"x",position=.1,relevance_score=70),
            PreparedMedia(2,"image","https://cdn.example.com/two.jpg",data=b"x",position=.2,relevance_score=70),
            PreparedMedia(3,"iframe","https://www.youtube.com/embed/AbCdEf12345",position=.3,relevance_score=80),
        ],
        video_preview=PreparedMedia(-1,"image","https://i.ytimg.com/vi/AbCdEf12345/hqdefault.jpg",data=b"x",relevance_score=80),
        video_link="https://www.youtube.com/watch?v=AbCdEf12345",
    )
    monkeypatch.setattr(legacy_media_pipeline,"prepare_article_media",lambda *a,**k: prepared)
    channel=SimpleNamespace(
        mode=ChannelMode.EDITORIAL,
        editorial_runtime_profile=EditorialRuntimeProfile.COMMERCIAL_EDITORIAL,
    )
    layout=json.dumps({
        "featured":"image|https://cdn.example.com/hero.jpg",
        "featured_meta":{"provenance":"body"},
        "blocks":[
            {"type":"media","kind":"image","url":"https://cdn.example.com/one.jpg","gallery":True},
            {"type":"media","kind":"image","url":"https://cdn.example.com/two.jpg","gallery":True},
            {"type":"media","kind":"iframe","url":"https://www.youtube.com/embed/AbCdEf12345","gallery":True},
        ],
    })
    article={"media_json":"[]","article_layout_json":layout,"title":"T","raw_text":"body","final_text":"done"}
    bundle=build_publication_media_bundle(channel,article)
    assert [x.url for x in bundle.items] == [
        "https://cdn.example.com/hero.jpg",
        "https://cdn.example.com/one.jpg",
        "https://cdn.example.com/two.jpg",
        "https://i.ytimg.com/vi/AbCdEf12345/hqdefault.jpg",
    ]
    assert bundle.video_link=="https://www.youtube.com/watch?v=AbCdEf12345"
    assert bundle.gallery_detected is True
    assert bundle.gallery_items_found == 3
    assert bundle.video_embed_count == 1


def test_rc112_fast_telegram_no_add_never_enters_empty_cooldown(tmp_path: Path) -> None:
    store=V2Store(tmp_path/"db.sqlite3")
    source_id=_seed_channel_source(store,kind="telegram")
    for _ in range(9):
        store.record_source_success(source_id,2000,items=40,added=0)
    row=store.source_health(source_id)
    assert row is not None
    assert row["cooldown_until"] == ""
    assert row["last_outcome"] == "OK"


def test_fast_web_known_only_never_enters_empty_cooldown(tmp_path: Path) -> None:
    store=V2Store(tmp_path/"db.sqlite3")
    source_id=_seed_channel_source(store,kind="page")
    for _ in range(9):
        store.record_source_success(source_id,2000,items=20,added=0)
        assert store.source_health(source_id)["cooldown_until"] == ""
    row=store.source_health(source_id)
    assert row["last_outcome"] == "KNOWN_ONLY"
    assert int(row["zero_result_streak"]) == 0


def test_rc112_startup_repair_clears_carried_empty_cooldowns(tmp_path: Path) -> None:
    store=V2Store(tmp_path/"db.sqlite3")
    source_id=_seed_channel_source(store,kind="telegram")
    with store.connect() as con:
        con.execute(
            """INSERT INTO source_health(source_id,cooldown_until,last_outcome,updated_at,zero_result_streak)
               VALUES(?,?,'EMPTY',?,9)
               ON CONFLICT(source_id) DO UPDATE SET cooldown_until=excluded.cooldown_until,last_outcome='EMPTY',
                   updated_at=excluded.updated_at,zero_result_streak=9""",
            (source_id,"2099-01-01T00:00:00+00:00",now_iso()),
        )
        con.execute("DELETE FROM meta WHERE key='rc112_cooldown_repair_v1'")
        store._ensure_rc112_cooldown_repair(con)
    row=store.source_health(source_id)
    assert row["cooldown_until"] == ""
    assert row["last_outcome"] == "OK"
    assert int(row["zero_result_streak"]) == 0


def test_rc112_view_gallery_control_recovers_preceding_hero_and_thumbnails() -> None:
    html = """
    <html><head><title>Wearable Stone Jackets</title></head><body>
      <article><h1>Wearable Stone Jackets</h1><p>Vollebak constructs a bomber from slate tiles.</p></article>
      <div class="visual-shell">
        <img src="https://cdn.example.com/rock-hero.jpg" width="1200" height="800" alt="Rock jacket"/>
        <img data-src="https://cdn.example.com/rock-1.jpg" width="90" height="90" alt=""/>
        <img data-src="https://cdn.example.com/rock-2.jpg" width="90" height="90" alt=""/>
        <img data-src="https://cdn.example.com/rock-3.jpg" width="90" height="90" alt=""/>
        <button>VIEW GALLERY</button>
      </div>
    </body></html>
    """
    out = extract_article_content(html, "https://www.trendhunter.com/trends/wearable-stone-jackets")
    layout = json.loads(out.layout_json)
    gallery = [b for b in layout["blocks"] if b.get("type") == "media" and b.get("gallery")]
    urls = [str(b.get("url") or "") for b in gallery]
    assert "https://cdn.example.com/rock-hero.jpg" in urls
    assert "https://cdn.example.com/rock-1.jpg" in urls
    assert "https://cdn.example.com/rock-2.jpg" in urls
    assert "https://cdn.example.com/rock-3.jpg" in urls


def test_rc112_commercial_gallery_weak_alt_survives_and_keeps_full_set(monkeypatch) -> None:
    import telegram_autopilot.media_pipeline as media_pipeline

    def fake_probe(item, *, marketing_context=False):
        item.mime_type = "image/jpeg"
        item.width = 1200
        item.height = 800
        item.digest = f"digest-{item.index}"
        item.data = b"image"
        return item

    monkeypatch.setattr(media_pipeline, "_probe_image", fake_probe)
    layout = json.dumps({
        "blocks": [
            {
                "type": "media", "index": idx, "kind": "image",
                "url": f"https://cdn.example.com/gallery-{idx}.jpg",
                "alt": "", "context": "visual-shell", "position": 0.8,
                "gallery": True,
            }
            for idx in range(1, 8)
        ]
    })
    prepared = media_pipeline.prepare_article_media(
        layout, [], title="Wearable Stone Jackets",
        article_text="Vollebak made a jacket from slate tiles.", marketing_context=True,
    )
    assert len(prepared.body) == 7
    assert all(item.gallery for item in prepared.body)
