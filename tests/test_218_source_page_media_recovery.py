import json
from types import SimpleNamespace

from telegram_autopilot.v2.domain import ChannelConfig, ChannelPolicy, ChannelMode
from telegram_autopilot.v2.publisher import Publisher


class FakeStore:
    def __init__(self, row):
        self.row = dict(row)
        self.updates = []

    def update_article(self, article_id, **fields):
        assert article_id == self.row["id"]
        self.updates.append(fields)
        self.row.update(fields)

    def get_article(self, article_id):
        return self.row


def channel(media="required", mode=ChannelMode.EDITORIAL):
    return ChannelConfig(id=27, name="Configured channel", telegram_chat_id="@fake",
                         mode=mode, policy=ChannelPolicy(media_policy=media))


def row():
    return dict(id=7, title="Generative art in a cave", raw_text="The story is about generative art in a cave.",
                media_json="[]", article_layout_json=json.dumps({"telegram_delivery": {"state": "UNKNOWN"},
                                                                  "media_recovery": {"attempts": 3}}))


def bundle(article, **kwargs):
    media = json.loads(article.get("media_json", "[]"))
    return SimpleNamespace(count=len(media))


def test_recovers_only_same_page_media_and_preserves_delivery(monkeypatch):
    import telegram_autopilot.v2.publisher as pub
    import telegram_autopilot.collector as collector
    store = FakeStore(row())
    monkeypatch.setattr(pub, "build_publication_media_bundle", bundle)
    monkeypatch.setattr(collector, "hydrate_article_page", lambda *a, **kw: SimpleNamespace(
        title=store.row["title"],
        media_urls=["https://cdn.example.com/story-image.jpg"],
        article_layout_json=json.dumps({"blocks": [{"type": "media", "url": "https://cdn.example.com/story-image.jpg"}],
                                        "featured_meta": {"provenance": "body"}})))
    article, media, outcome = Publisher(store)._recover_missing_source_media(
        channel(), store.row, "https://example.com/story", set())
    assert outcome == "recovered"
    assert media.count == 1
    layout = json.loads(article["article_layout_json"])
    assert layout["telegram_delivery"]["state"] == "UNKNOWN"
    assert layout["media_recovery"]["attempts"] == 3
    assert article["title"] == "Generative art in a cave"


def test_mismatched_page_fails_closed(monkeypatch):
    import telegram_autopilot.v2.publisher as pub
    import telegram_autopilot.collector as collector
    store = FakeStore(row())
    monkeypatch.setattr(pub, "build_publication_media_bundle", bundle)
    monkeypatch.setattr(collector, "hydrate_article_page", lambda *a, **kw: SimpleNamespace(
        title="Unrelated page", media_urls=["https://cdn.example.com/other.jpg"],
        article_layout_json='{"article_identity":{"status":"MISMATCH"}}'))
    _, media, outcome = Publisher(store)._recover_missing_source_media(
        channel(), store.row, "https://example.com/story", set())
    assert outcome == "identity_mismatch"
    assert media.count == 0
    assert not store.updates


def test_optional_media_never_trigger_refetch(monkeypatch):
    import telegram_autopilot.v2.publisher as pub
    import telegram_autopilot.collector as collector
    monkeypatch.setattr(pub, "build_publication_media_bundle", bundle)
    monkeypatch.setattr(collector, "hydrate_article_page", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("unexpected fetch")))
    store = FakeStore(row())
    _, media, outcome = Publisher(store)._recover_missing_source_media(
        channel("optional"), store.row, "https://example.com/story", set())
    assert outcome == "not_needed" and media.count == 0
