"""v2.2.34: isolated Drive OAuth and positively linked monitoring media."""
import json
from types import SimpleNamespace

from telegram_autopilot.media import encode_media
from telegram_autopilot.v2 import drive_api_telemetry as drive
from telegram_autopilot.v2.domain import ChannelMode
from telegram_autopilot.v2.ingest import TelegramEntry
from telegram_autopilot.v2.strict_ingest import (
    _explicit_same_channel_media_links,
    strict_stitch_telegram,
)
from telegram_autopilot.v2.telegram_media_publish_guard import _verified_split_media


def test_drive_never_discovers_companion_app(monkeypatch):
    monkeypatch.setattr(drive, "_own_credentials", lambda: None)
    monkeypatch.setattr(drive, "_environment_credentials", lambda: None)
    assert drive._credential_candidates() == []
    assert drive.discover_drive_credentials(persist_companion=True) is None


def test_legacy_autopilot_credentials_are_preserved_for_safe_migration(monkeypatch):
    legacy = drive.DriveCredentials("own-client", "", "stored-legacy-refresh", source="legacy-unverified")
    monkeypatch.setattr(drive, "_own_credentials", lambda: legacy)
    monkeypatch.setattr(drive, "_environment_credentials", lambda: None)
    assert drive.discover_drive_credentials() == legacy
    assert drive._credential_candidates() == [legacy]


def test_autopilot_does_not_fall_back_to_sibling_token_after_expiration(monkeypatch):
    legacy = drive.DriveCredentials("own-client", "", "revoked", source="legacy-unverified")
    monkeypatch.setattr(drive, "_own_credentials", lambda: legacy)
    monkeypatch.setattr(drive, "_environment_credentials", lambda: None)

    def denied(url, fields, **kwargs):
        raise drive.DriveTelemetryError("invalid_grant")

    monkeypatch.setattr(drive, "_post_form", denied)
    transport = drive.DirectDriveTelemetry("test", folder_id="folder")
    try:
        transport._token()
    except drive.DriveTelemetryError as exc:
        assert "invalid_grant" in str(exc)
    else:
        raise AssertionError("expired Autopilot token must not silently borrow Content Tool access")


def _entry(post_id, text="", media=(), reply="", grouped=""):
    return TelegramEntry(
        post=f"community/{post_id}", text=text,
        published=f"2026-10-25T12:00:{post_id % 60:02d}+00:00",
        media=list(media), reply_to_post=reply, grouped_id=grouped,
    )


def test_explicit_photo_link_joins_split_media_and_text():
    image = encode_media("image", "https://cdn.example.org/photo.jpg")
    text = "Світлини з навчання: https://t.me/community/100"
    posts = [_entry(100, media=[image]), _entry(101, text=text)]
    result = strict_stitch_telegram("community", posts)
    assert len(result) == 1
    assert result[0].media_urls == [image]
    layout = json.loads(result[0].article_layout_json)
    assert layout["telegram"]["message_ids"] == ["100", "101"]
    assert len(layout["telegram"]["source_message_records_v1"]) == 2


def test_neighbor_photo_without_link_is_not_borrowed():
    image = encode_media("image", "https://cdn.example.org/unrelated.jpg")
    result = strict_stitch_telegram("community", [
        _entry(100, media=[image]), _entry(101, text="Навчання відбулося в громаді.")
    ])
    assert len(result) == 1
    assert not result[0].media_urls
    assert _explicit_same_channel_media_links("community", "Новини: https://t.me/community/100") == set()


def test_split_monitoring_publish_keeps_proven_media_but_not_others():
    real = encode_media("image", "https://cdn.example.org/proven.jpg")
    unrelated = encode_media("image", "https://cdn.example.org/unrelated.jpg")
    layout = json.dumps({"telegram": {"source_message_records_v1": [
        {"post": "community/101", "text": "Фото: https://t.me/community/100", "media": []},
        {"post": "community/100", "text": "", "media": [real], "reply_to_post": ""},
    ]}})
    article = {"article_layout_json": layout}
    channel = SimpleNamespace(mode=ChannelMode.MONITORING)
    assert _verified_split_media(article, SimpleNamespace(count=1, encoded_items=[real]), "https://t.me/community/101", channel)
    assert not _verified_split_media(article, SimpleNamespace(count=1, encoded_items=[unrelated]), "https://t.me/community/101", channel)
    assert not _verified_split_media(article, SimpleNamespace(count=1, encoded_items=[real]), "https://t.me/other/101", channel)
    assert not _verified_split_media(article, SimpleNamespace(count=1, encoded_items=[real]), "https://t.me/community/101", SimpleNamespace(mode=ChannelMode.EDITORIAL))
