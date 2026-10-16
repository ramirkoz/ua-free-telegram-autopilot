"""2.1.18: editorial trust belongs to each claim, not the newsroom's ownership."""
import json
from types import SimpleNamespace

from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode, ChannelPolicy
from telegram_autopilot.v2.editorial import hard_editorial_reject
from telegram_autopilot.v2.storage import V2Store


def _channel():
    return ChannelConfig(
        id=3, name="ЗАПОРІЖЖЯ | ГРОМАДИ", telegram_chat_id="@test",
        mode=ChannelMode.MONITORING,
        policy=ChannelPolicy(monitoring_source_policy="connected_original"),
    )


def _item(name, text, *, forwarded=False):
    return SimpleNamespace(
        title="Новина Запоріжжя", source_name=name,
        source_url="https://t.me/newsroom/123", raw_text=text,
        article_layout_json=json.dumps({"telegram": {"forwarded": forwarded}}),
    )


def test_original_local_media_can_be_selected():
    for name in ("ЗаБор Запоріжжя", "БЕЗ БАЙДИ", "5 РЕДАКЦІЯ", "ЗАПОРІЖЖЯ.INFO", "INFORM.ZP"):
        item = _item(name, "У Запоріжжі відкрили новий центр допомоги родинам. Центр надаватиме консультації та інформацію про виплати.")
        assert not hard_editorial_reject(_channel(), item), name


def test_reader_and_local_rumors_still_rejected():
    for content in (
        "Підписники пишуть, що на вулиці зникло світло та чути дивні звуки.",
        "Місцеві повідомляють, що біля парку трапилася якась подія.",
        "За словами очевидців, на вулиці помітили незвичайну ситуацію.",
        "Мешканці кажуть, що в районі перекрили дорогу.",
    ):
        assert hard_editorial_reject(_channel(), _item("ЗаБор Запоріжжя", content)) == "MONITORING_READER_RUMOR_NOT_OFFICIAL"


def test_independently_confirmed_local_reports_can_be_assessed():
    item = _item("5 РЕДАКЦІЯ", "Місцеві повідомляють про зміни руху. Поліція підтвердила перекриття та опублікувала схему об'їзду.")
    assert hard_editorial_reject(_channel(), item) != "MONITORING_READER_RUMOR_NOT_OFFICIAL"


def test_forwarded_newsroom_post_remains_blocked():
    assert hard_editorial_reject(_channel(), _item(
        "ЗаБор Запоріжжя",
        "У Запоріжжі відкрили центр підтримки жителів із консультаціями та допомогою.",
        forwarded=True,
    )) == "MONITORING_NOT_ORIGINAL_FORWARD"


def test_migrates_only_named_community_channel_and_preserves_explicit_policy(tmp_path):
    store = V2Store(tmp_path / "monitoring.sqlite3")
    with store.connect() as con:
        con.execute("INSERT INTO channels(id,name,telegram_chat_id,channel_mode,created_at,updated_at) VALUES(3,'ЗАПОРІЖЖЯ | ГРОМАДИ','@community','monitoring','now','now')")
        con.execute("INSERT INTO channels(id,name,telegram_chat_id,channel_mode,created_at,updated_at) VALUES(4,'Other monitoring','@other','monitoring','now','now')")
        con.execute("INSERT INTO channel_policies(channel_id,monitoring_source_policy,updated_at) VALUES(3,'institutional','now')")
        con.execute("INSERT INTO channel_policies(channel_id,monitoring_source_policy,updated_at) VALUES(4,'institutional','now')")
        con.execute("DELETE FROM meta WHERE key='v2118_community_news_sources_v1'")
        V2Store._ensure_v2118_community_news_sources(con)
        V2Store._ensure_v2118_community_news_sources(con)
        assert con.execute("SELECT monitoring_source_policy FROM channel_policies WHERE channel_id=3").fetchone()[0] == "connected_original"
        assert con.execute("SELECT monitoring_source_policy FROM channel_policies WHERE channel_id=4").fetchone()[0] == "institutional"
    assert store.get_channel(3).policy.monitoring_source_policy == "connected_original"
