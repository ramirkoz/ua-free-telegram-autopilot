import json

from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode, ChannelPolicy
from telegram_autopilot.v2.editorial import hard_editorial_reject
from telegram_autopilot.v2.storage import V2Store


def channel(denied="V_Zelenskiy_official", mode=ChannelMode.MONITORING):
    return ChannelConfig(id=123, name="Configured monitoring channel", telegram_chat_id="@example",
                         mode=mode, policy=ChannelPolicy(monitoring_denied_origins=denied))


def article(source, *, metadata=None, text=None):
    return {"source_url": source, "canonical_source_url": source, "title": "Офіційне повідомлення",
            "raw_text": text or "Офіційні представники повідомили результати зустрічі та оприлюднили подробиці переговорів.",
            "article_layout_json": json.dumps({"telegram": metadata or {}})}


def test_direct_denied_original():
    assert hard_editorial_reject(channel(), article("https://t.me/V_Zelenskiy_official/17777")) == "MONITORING_REPOST_DENYLIST_SOURCE"


def test_forwarded_original_via_official_community_source():
    item = article("https://t.me/community_official/998", metadata={
        "forwarded": True, "forward_from": "V_Zelenskiy_official"})
    assert hard_editorial_reject(channel(), item) == "MONITORING_REPOST_DENYLIST_SOURCE"


def test_forwarded_link_attribution():
    item = article("https://t.me/community_official/998",
        text="Переслано з https://t.me/V_Zelenskiy_official/17777, повідомлено про зустріч.",
        metadata={"forwarded": True})
    assert hard_editorial_reject(channel(), item) == "MONITORING_REPOST_DENYLIST_SOURCE"


def test_source_mention_in_local_original_not_automatically_denied():
    item = article("https://t.me/community_official/999",
                   text="Міська рада повідомила про місцевий захід. Канал https://t.me/V_Zelenskiy_official згадано лише як посилання.")
    assert hard_editorial_reject(channel(), item) != "MONITORING_REPOST_DENYLIST_SOURCE"


def test_editorial_channel_untouched():
    assert hard_editorial_reject(channel(mode=ChannelMode.EDITORIAL),
                                article("https://t.me/V_Zelenskiy_official/33")) != "MONITORING_REPOST_DENYLIST_SOURCE"


def test_policy_persists_and_one_time_migration(tmp_path):
    db = V2Store(tmp_path / "monitoring.sqlite3")
    with db.connect() as con:
        con.execute("INSERT INTO channels(id,name,telegram_chat_id,channel_mode,created_at,updated_at) VALUES(123,'Monitor','@test','monitoring','now','now')")
        con.execute("INSERT INTO channels(id,name,telegram_chat_id,channel_mode,created_at,updated_at) VALUES(124,'Editor','@test2','editorial','now','now')")
        con.execute("INSERT INTO channel_policies(channel_id) VALUES(123)")
        con.execute("INSERT INTO channel_policies(channel_id) VALUES(124)")
        con.execute("DELETE FROM meta WHERE key='v2113_monitor_denied_origins_default_v1'")
        V2Store._ensure_v2113_monitoring_denied_origins(con)
        assert con.execute("SELECT monitoring_denied_origins FROM channel_policies WHERE channel_id=123").fetchone()[0] == "V_Zelenskiy_official"
        assert con.execute("SELECT monitoring_denied_origins FROM channel_policies WHERE channel_id=124").fetchone()[0] == ""
    cfg = db.get_channel(123)
    assert cfg.policy.monitoring_denied_origins == "V_Zelenskiy_official"
    cfg.policy.monitoring_denied_origins = "another_source"
    db.save_channel(cfg)
    assert db.get_channel(123).policy.monitoring_denied_origins == "another_source"
