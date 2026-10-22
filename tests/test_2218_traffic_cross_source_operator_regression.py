from datetime import datetime, timezone, timedelta
"""22 October 2026 operator screenshot regression: the same dam video was posted twice.

First: #73290 from ZapoLife, Telegram #3388 at 10:06:10.
Second: #73267 from info_zp, Telegram #3400 at 10:49:37.

Prior prepublish matched nearest_published_article_id=73290 but logged
"concepts=5/0.50 entities=- taxa=- rare=0" and sent anyway. Both are a
DTP+jam at the dam with queue starting at the Kakhovska road ring.
"""
from __future__ import annotations

from telegram_autopilot.v2.traffic_incident_identity import traffic_incident_same_event, transient_traffic_age_exclusion
from telegram_autopilot.v2.event_dedupe_guard import event_fingerprint_same_event

PUBLISHED = {
    "id": 73290, "source_id": 193, "channel_id": 3,
    "source_name": "Запоріжжя Online",
    "title": "⛔️ На греблі ДніпроГЕС фіксують затор через дорожню аварію",
    "raw_text": ("Запоріжці повідомляють про ускладнення руху "
                 "від кільця на вулиці Каховській. Відео: Запоріжжя. Інфо"),
    "source_published_at": "2026-10-22T09:47:53+03:00",
    "published_at": "2026-10-22T10:06:10+03:00",
    "final_text": ("На греблі ДніпроГЕС утворився затор через дорожню аварію. "
                   "Запоріжці повідомляють про ускладнення руху, яке починається "
                   "від кільця на вулиці Каховській."),
}
RECURRENT = {
    "id": 73267, "source_id": 190, "channel_id": 3,
    "source_name": "ЗАПОРІЖЖЯ.ІНФО",
    "title": "❗️ДТП на греблі, з правого на лівий берег. Затор з кільця Каховській!",
    "raw_text": "❗️ДТП на греблі, з правого на лівий берег. Затор з кільця Каховській!",
    "source_published_at": "2026-10-22T08:56:02+03:00",
    "published_at": "2026-10-22T10:49:37+03:00",
    "final_text": ("На греблі сталася ДТП під час руху з правого на лівий берег. "
                   "Затор — від кільця в бік Каховської."),
}


def test_real_two_operator_posts_are_one_event_cross_source():
    same, reason = traffic_incident_same_event(RECURRENT, PUBLISHED)
    assert same, reason
    same, reason = event_fingerprint_same_event(RECURRENT, PUBLISHED)
    assert same, reason
    assert "traffic" in reason


def test_durable_published_ledger_row_still_blocks_at_prepublish():
    # The published_event_ledger has neither source_published_at nor URLs.
    # The match must rely on durable source-owned text and published_at.
    durable = {key: PUBLISHED[key] for key in (
        "id", "source_id", "channel_id", "title", "raw_text", "final_text", "published_at"
    )}
    same, reason = event_fingerprint_same_event(RECURRENT, durable)
    assert same, reason


def test_same_video_brand_or_source_name_does_not_prove_event_identity():
    wrong = dict(PUBLISHED,
        title="На греблі ДніпроГЕС планують ремонт наступного тижня",
        raw_text="Місцевий канал додав відео із затором, але без факту нового ДТП."
    )
    assert not traffic_incident_same_event(RECURRENT, wrong)[0]


def test_different_road_approach_not_silenced():
    wrong = dict(PUBLISHED, raw_text="Черга авто починається від кільця на вулиці Північній.")
    assert not traffic_incident_same_event(RECURRENT, wrong)[0]


def test_opposite_explicit_directions_mean_different_reports():
    other = dict(PUBLISHED,
        raw_text="ДТП та затор з кільця на вулиці Каховській з лівого на правий берег."
    )
    assert not traffic_incident_same_event(RECURRENT, other)[0]


def test_opened_road_is_material_update_not_duplicate():
    other = dict(PUBLISHED,
        raw_text="Після ДТП затор від кільця на вулиці Каховській зник. Рух відновили."
    )
    assert not traffic_incident_same_event(RECURRENT, other)[0]


def test_second_crash_explicitly_reported_as_new_event():
    other = dict(PUBLISHED,
        raw_text="Ще одна ДТП на греблі ДніпроГЕС, затор від кільця на вулиці Каховській."
    )
    assert not traffic_incident_same_event(RECURRENT, other)[0]


def test_repeated_crash_at_same_location_next_day_is_separate():
    old = dict(PUBLISHED, published_at="2026-10-21T10:06:10+03:00",
               source_published_at="2026-10-21T09:47:53+03:00")
    assert not traffic_incident_same_event(RECURRENT, old)[0]


def test_congested_dam_without_named_approach_not_enough():
    other = dict(PUBLISHED,
        raw_text="ДТП на греблі ДніпроГЕС, затор у напрямку міста."
    )
    assert not traffic_incident_same_event(RECURRENT, other)[0]


def test_municipal_transport_restriction_without_dtp_not_collapsed():
    other = dict(PUBLISHED,
        title="Гребля ДніпроГЕС перекрита на ремонт",
        raw_text="Затор від кільця Каховській через дорожні роботи."
    )
    assert not traffic_incident_same_event(RECURRENT, other)[0]


def test_same_publisher_new_row_not_mistaken_as_cross_source_event():
    other = dict(PUBLISHED, source_id=RECURRENT["source_id"])
    assert not traffic_incident_same_event(RECURRENT, other)[0]


def test_operator_stale_0856_jam_1049_blocked_but_first_fresh_post_allowed():
    now = datetime.fromisoformat("2026-10-22T10:49:37+03:00")
    assert transient_traffic_age_exclusion(RECURRENT, now=now).startswith("MONITORING_STALE_TRAFFIC")
    earlier = datetime.fromisoformat("2026-10-22T10:06:10+03:00")
    assert transient_traffic_age_exclusion(PUBLISHED, now=earlier)==""


def test_official_enduring_closure_and_settled_traffic_update_are_not_expired():
    now = datetime.fromisoformat("2026-10-22T12:30:00+03:00")
    closure=dict(RECURRENT,raw_text=RECURRENT["raw_text"] +
                 " Через ДТП офіційно обмежено рух транспорту; змінено маршрут автобусів.")
    assert not transient_traffic_age_exclusion(closure,now=now)
    reopened=dict(RECURRENT,raw_text=RECURRENT["raw_text"]+" Рух відновили після усунення аварії.")
    assert not transient_traffic_age_exclusion(reopened,now=now)


def test_stale_guard_does_not_ban_other_news_or_guess_timestamp():
    now=datetime.fromisoformat("2026-10-22T12:30:00+03:00")
    other=dict(RECURRENT,raw_text="У Запоріжжі 22 жовтня відкрили новий центр підтримки.")
    other["title"]=other["raw_text"]
    assert not transient_traffic_age_exclusion(other,now=now)
    no_time=dict(RECURRENT)
    no_time.pop("source_published_at")
    assert not transient_traffic_age_exclusion(no_time,now=now)
    no_tz=dict(RECURRENT,source_published_at="2026-10-22T08:56:02")
    assert not transient_traffic_age_exclusion(no_tz,now=now)


def test_live_now_gate_preai_and_pretelegram_accepts_fresh_rejects_old():
    from telegram_autopilot.v2.monitoring_live_now import live_now_exclusion
    from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode, ChannelPolicy
    channel=ChannelConfig(
        id=3,name="ЗАПОРІЖЖЯ | ГРОМАДИ",telegram_chat_id="-1001",
        mode=ChannelMode.MONITORING,policy=ChannelPolicy(
            channel_id=3,rejection_rules="[LIVE_NOW_RC96]"
        ))
    old=dict(RECURRENT,source_published_at=(
        datetime.now(timezone.utc)-timedelta(minutes=105)
    ).isoformat())
    assert "MONITORING_STALE_TRAFFIC" in live_now_exclusion(channel,old)
    fresh=dict(RECURRENT,source_published_at=(
        datetime.now(timezone.utc)-timedelta(minutes=5)
    ).isoformat())
    assert "MONITORING_STALE_TRAFFIC" not in live_now_exclusion(channel,fresh)
    optout=ChannelConfig(
        id=3,name="Other",telegram_chat_id="-1002",
        mode=ChannelMode.MONITORING,policy=ChannelPolicy(channel_id=3)
    )
    assert not live_now_exclusion(optout,old)
