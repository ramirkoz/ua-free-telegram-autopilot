import json

from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode, ChannelPolicy
from telegram_autopilot.v2.editorial import _monitoring_official_context_reject, hard_editorial_reject
from telegram_autopilot.v2.storage import V2Store


def channel(mode: str):
    return ChannelConfig(
        id=42, name="Any channel", telegram_chat_id="@example", mode=ChannelMode.MONITORING,
        policy=ChannelPolicy(channel_id=42, monitoring_source_policy=mode),
    )


def item(text, *, forwarded=False):
    return {
        "title": text, "raw_text": text,
        "source_name": "Regional newsroom",
        "source_url": "https://t.me/regional_editor/987",
        "article_layout_json": json.dumps({"telegram": {"forwarded": forwarded}}),
    }


def test_default_source_gate_remains_conservative():
    text = "У громаді відкрили новий медичний пункт та оприлюднили адресу прийому мешканців."
    assert hard_editorial_reject(channel("institutional"), item(text)) == "MONITORING_SOURCE_NOT_OFFICIAL"


def test_operator_can_allow_originals_from_configured_sources():
    text = "У громаді відкрили новий медичний пункт та оприлюднили адресу прийому мешканців."
    assert not hard_editorial_reject(channel("connected_original"), item(text))
    assert hard_editorial_reject(channel("connected_original"), item(text, forwarded=True)) == "MONITORING_NOT_ORIGINAL_FORWARD"


def test_source_policy_does_not_disable_unverified_rumour_gate():
    assert _monitoring_official_context_reject(
        item("За словами читачів, у місті зникло світло. Підписники повідомили про відключення."),
        channel("connected_original"),
    ) == "MONITORING_READER_RUMOR_NOT_OFFICIAL"


def test_invalid_policy_fails_closed():
    assert channel("unknown_mode").policy.normalized_monitoring_source_policy() == "institutional"


def test_channel_source_policy_roundtrips_through_database(tmp_path):
    store = V2Store(tmp_path / "source_policy.sqlite3")
    with store.connect() as con:
        con.execute("INSERT INTO channels(id,name,telegram_chat_id,created_at,updated_at) VALUES(42,'Any','@example','2026-10-13','2026-10-13')")
    store.save_channel(channel("connected_original"))
    fresh = V2Store(tmp_path / "source_policy.sqlite3")
    loaded = fresh.get_channel(42)
    assert loaded is not None
    assert loaded.policy.normalized_monitoring_source_policy() == "connected_original"
