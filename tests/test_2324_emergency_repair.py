"""v2.3.24 LIVE production regressions: unrelated/repeated images and overblocking.

Offline tests only. No network, AI provider, live Telegram or operator Data.
"""
import json
import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from telegram_autopilot.media import canonical_asset_key
from telegram_autopilot.media_pipeline import PreparedMedia, _in_story_gallery, _semantic_media_match, prepare_article_media
from telegram_autopilot.v2.private_document_contact_2322 import no_announcement_reason_2322
from telegram_autopilot.v2.science_reader_clarity_243 import science_plain_language_issue
from telegram_autopilot.v2.editorial_hard_floor import two_sentence_reason
from telegram_autopilot.v2.storage import V2Store

BLACK = "https://cdn.mos.cms.futurecdn.net/flexiimages/h0mke6edxz1770889266-400-80.jpg"
RESIZED = "https://cdn.mos.cms.futurecdn.net/flexiimages/h0mke6edxz1770889266-800-90.jpg"
SOURCE = "https://www.creativebloq.com/how-to/this-artist-specialises-in-creating-an-epic-sense-of-scale-in-3d-scenes"


def test_blank_gallery_does_not_override_article_ownership():
    candidate = PreparedMedia(1, "image", BLACK, gallery=True, context="related-trends rail", position=.9)
    assert not _in_story_gallery(candidate, title="Gate of Vanaheimr", article_text="Borisut Blender")
    authentic = PreparedMedia(1, "image", BLACK, gallery=True, context="visual-shell", position=.1)
    assert _in_story_gallery(authentic, title="Gate of Vanaheimr", article_text="Borisut Blender")


def test_weak_commercial_gallery_cannot_publish_black_gadgets_for_vanaheimr():
    layout = json.dumps({"blocks": [{"type": "media", "kind": "image", "url": BLACK, "gallery": True, "alt": "", "caption": "", "position": .12}]})

    def probe(item, **kwargs):
        item.data = b"safe"; item.width = 1000; item.height = 750; item.digest = "known"
        return item

    with patch("telegram_autopilot.media_pipeline._probe_article_image", side_effect=probe):
        result = prepare_article_media(layout, [BLACK], title="Borisut Gate of Vanaheimr",
                                       article_text="Borisut creates a fantasy world in Blender.",
                                       source_url=SOURCE, marketing_context=True, excluded_urls={RESIZED})
    assert not result.body


def test_original_story_art_can_pass_semantic_gallery_check():
    item = PreparedMedia(1, "image", "https://example.org/gate-of-vanaheimr.jpg",
                         gallery=True, context="article gallery",
                         alt="Borisut Gate of Vanaheimr scene", position=.15)
    assert _in_story_gallery(item, title="Gate of Vanaheimr",
                             article_text="Borisut creates a fantasy world in Blender")


def test_asset_key_catches_resized_sitewide_photo():
    assert canonical_asset_key(BLACK) == canonical_asset_key(RESIZED)


def test_lost_pets_stay_out_of_news():
    for text in ("Пропала чорна кішка, допоможіть знайти.",
                 "Зник чорний кіт, хто бачив?",
                 "Пропав пес біля лікарні."):
        assert no_announcement_reason_2322({"title": text, "raw_text": text}) == "MONITORING_CLASSIFIED_LOST_FOUND_2322"
    assert no_announcement_reason_2322({"title": "Поліція врятувала кота",
                                         "raw_text": "Кота після пожежі оглянули ветеринари."}) == ""


def test_known_hardware_manufacturer_does_not_erase_science_news():
    assert science_plain_language_issue("AMD презентувала нові процесори для комп’ютерів.") == ""
    assert science_plain_language_issue("Дослідники використали метод XYZ без пояснення.").startswith("SCIENCE_READER_ACRONYM")


def test_verified_utility_schedule_not_discarded_for_nonprose_format():
    row = {"title": "Графік відключення світла",
           "raw_text": "Графік відключення світла:\nЧерга 1.1 з 06:00 до 10:00\nЧерга 2.1 з 10:00 до 14:00"}
    assert two_sentence_reason(row) == ""
    assert two_sentence_reason({"title": "Оголошення", "raw_text": "Лише одна фраза."}) == "EDITORIAL_MIN_TWO_SENTENCES: source"


class _StoreStub:
    def __init__(self, path):
        self.path = path

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            yield db
        finally:
            db.close()

    def get_article(self, article_id):
        with self.connect() as db:
            return db.execute("SELECT * FROM articles WHERE id=?", (article_id,)).fetchone()

    _ensure_published_web_media_2324 = V2Store._ensure_published_web_media_2324


def test_cross_article_published_hash_ledger_blocks_reuse():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "data.db"
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE articles(id INTEGER,source_id INTEGER,channel_id INTEGER,source_url TEXT,canonical_source_url TEXT,media_json TEXT,article_layout_json TEXT,published_at TEXT)")
            db.execute("INSERT INTO articles VALUES(1,200,2,'https://site.test/story1','https://site.test/story1','[]','{}','2026')")
            db.execute("INSERT INTO articles VALUES(2,200,2,'https://site.test/story2','https://site.test/story2','[]','{}','')")
        db.close()  # sqlite3.Connection context manager commits but does not close on Windows
        store = _StoreStub(path)
        first = SimpleNamespace(kind="image", source_url=BLACK, digest="same-binary-sha")
        same_pixels_new_url = SimpleNamespace(kind="image", source_url="https://other.test/photo.jpg", digest="same-binary-sha")
        assert not V2Store.repeated_published_web_media_2324(store, 2, [same_pixels_new_url])
        V2Store.remember_published_web_media_2324(store, 1, [first])
        assert V2Store.repeated_published_web_media_2324(store, 2, [same_pixels_new_url])
        assert not V2Store.repeated_published_web_media_2324(store, 1, [first])
