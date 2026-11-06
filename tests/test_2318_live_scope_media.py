"""2.3.18: LIVE #92376/#92398/#92442 regressions, no external I/O."""
from __future__ import annotations

import json

from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode, ChannelPolicy
from telegram_autopilot.v2.editorial import _postfactum_security_policy
from telegram_autopilot.v2.editorial_copyedit_237 import (
    safe_copyedit_237,
    copyedit_issues_237,
)
from telegram_autopilot.v2.monitoring_live_now import (
    civic_shelter_plan_not_alert_2318, live_now_exclusion,
)
from telegram_autopilot.v2.monitoring_source_scope_2317 import (
    monitoring_source_scope_reason_2317,
)
from telegram_autopilot.v2.ready_backlog import ReadyBacklogStore


def monitoring():
    return ChannelConfig(
        id=3, name="Регіональні новини", telegram_chat_id="-100333",
        mode=ChannelMode.MONITORING,
        policy=ChannelPolicy(channel_id=3, rejection_rules="[LIVE_NOW_RC96]"),
    )


def source(title, body):
    return {"title": title, "raw_text": body, "source_name": "місцеве видання"}


def test_planned_shelter_with_incidental_alert_purpose_is_a_local_civic_story():
    article = source(
        "У центрі Запоріжжя встановлять нове модульне укриття",
        "Готуються роботи з облаштування нового модульного укриття у центрі Запоріжжя "
        "на майдані Митців. Захисна споруда має стати місцем, де пішоходи "
        "зможуть перечекати повітряну тривогу.",
    )
    assert civic_shelter_plan_not_alert_2318(article["raw_text"])
    assert live_now_exclusion(monitoring(), article) == ""
    assert _postfactum_security_policy(monitoring(), article) == ""
    assert monitoring_source_scope_reason_2317(monitoring(), article) == ""


def test_ongoing_air_raid_with_shelter_mention_still_rejected():
    article = source(
        "У Запоріжжі встановлять модульне укриття",
        "Місто планує укриття, щоб перечекати повітряну тривогу. "
        "Зараз у Запоріжжі оголосили повітряну тривогу, летять дрони.",
    )
    assert not civic_shelter_plan_not_alert_2318(article["raw_text"])
    assert live_now_exclusion(monitoring(), article)


def test_nonlocal_weather_rejected_only_on_original_source_scope():
    foreign = source(
        "На Львівщині та Івано-Франківщині випав сніг",
        "На Черкащині сніг із дощем. У західних областях засніжені краєвиди. "
        "Завтра по всій Україні очікують мокрий сніг.",
    )
    assert monitoring_source_scope_reason_2317(monitoring(), foreign) == (
        "MONITORING_NONLOCAL_UA_WEATHER_2318"
    )
    local = source(
        "У Запорізькій області очікують мокрий сніг",
        "На Львівщині випав сніг, а Запоріжжя 7 листопада очікує мокрий сніг і ожеледицю.",
    )
    assert monitoring_source_scope_reason_2317(monitoring(), local) == ""
    national_law = source(
        "Уряд затвердив новий порядок допомоги переселенцям",
        "Постанову Кабміну застосовуватимуть по всій Україні, зокрема для ВПО.",
    )
    assert monitoring_source_scope_reason_2317(monitoring(), national_law) == ""


def test_attested_split_word_is_repaired_without_language_guessing():
    broken = "На Львівщині ви\nпав сніг, а на Черкащині йшов дощ."
    assert "випав сніг" in safe_copyedit_237(broken)
    assert copyedit_issues_237(broken)
    assert not copyedit_issues_237(safe_copyedit_237(broken))


def test_download_retry_cannot_be_rearmed_by_same_or_new_source_urls(tmp_path):
    store = ReadyBacklogStore(tmp_path / "safe.db")
    with store.connect() as con:
        con.execute(
            "INSERT INTO channels(id,name,telegram_chat_id,channel_mode,created_at,updated_at) "
            "VALUES(1,'CTRL+UA','@ctrl','editorial','now','now')"
        )
        con.execute(
            "INSERT INTO sources(id,channel_id,kind,name,url) "
            "VALUES(69,1,'rss','The Decoder','https://example.test/feed')"
        )
    options = dict(
        channel_id=1, source_id=69, external_id="article-92442",
        title="Test source media", source_url="https://example.test/story",
        raw_text="This source includes four images for one article.",
        media_json=json.dumps(["https://example.test/1.jpg", "https://example.test/2.jpg"]),
        article_layout_json="{}",
    )
    article_id = store.insert_collected(**options)
    due = "2099-11-06T16:17:55+00:00"
    store.update_article(
        article_id, stage="READY", decision="PUBLISH",
        blocked_by="MEDIA", last_error_code="MEDIA_DOWNLOAD_RETRY", next_retry_at=due,
    )
    assert store.ready_articles(1) == []
    assert not store._recover_ready_media_blocker(article_id, fresh_media=options["media_json"])
    # A feed refresh can change source URLs, but it cannot prove that the
    # fourth binary will download; honor the original backoff.
    options["media_json"] = json.dumps([
        "https://example.test/1.jpg", "https://example.test/2.jpg",
        "https://example.test/new.jpg",
    ])
    assert store.insert_collected(**options) == article_id
    row = store.get_article(article_id)
    assert row["blocked_by"] == "MEDIA"
    assert row["last_error_code"] == "MEDIA_DOWNLOAD_RETRY"
    assert row["next_retry_at"] == due
    assert store.ready_articles(1) == []
