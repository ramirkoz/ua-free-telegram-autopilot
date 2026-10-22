"""2.2.19 LIVE screenshot fixture: one repatriation, two Telegram sources.

Operator #74213 BEZ BAIDY was published at 13:30, #74233 Zabоr ZP at
13:53, both describing exactly the same return of 252 sets of remains.
The existing final published-ledger nearest match was #74213, but only
five shared concepts/0.50 and no blocking action.
"""
from __future__ import annotations

from telegram_autopilot.v2.repatriation_event_identity import (
    remains_return_count, repatriation_same_event,
)
from telegram_autopilot.v2.event_dedupe_guard import event_fingerprint_same_event
from telegram_autopilot.v2.monitoring_civic_quality import civic_relevance_exclusion
from telegram_autopilot.v2.monitoring_live_now import live_now_exclusion
from telegram_autopilot.v2.editorial import hard_editorial_reject, prepublish_quality_issues
from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode, ChannelPolicy

FIRST = {
    "id": 74213, "channel_id": 3, "source_id": 197,
    "title": "🕯️В Україну повернули тіла 252 загиблих військових, — Коордштаб",
    "raw_text": "🕯️В Україну повернули тіла 252 загиблих військових, — Коордштаб",
    "final_text": "В Україну повернули тіла 252 полеглих військових, повідомили в Координаційному штабі.",
    "source_published_at": "2026-10-22T13:00:34+03:00",
    "published_at": "2026-10-22T13:30:31+03:00",
}
SECOND = {
    "id": 74233, "channel_id": 3, "source_id": 191,
    "title": "🚧😢🇺🇦В Україну повернули тіла ще 252 людей, які, за твердженням РФ, належать українським військовослужбовцям, — Координаційний штаб.",
    "raw_text": "🚧😢🇺🇦В Україну повернули тіла ще 252 людей, які, за твердженням РФ, належать українським військовослужбовцям, — Координаційний штаб.",
    "source_published_at": "2026-10-22T13:17:07+03:00",
    "published_at": "2026-10-22T13:53:08+03:00",
}


def monitoring(opt_in=True, mode=ChannelMode.MONITORING):
    return ChannelConfig(
        id=3, name="ЗАПОРІЖЖЯ | ГРОМАДИ", telegram_chat_id="-1000", mode=mode,
        policy=ChannelPolicy(
            channel_id=3,
            rejection_rules="[LIVE_NOW_RC96] Моніторинг місцевих подій" if opt_in else "",
        ),
    )


def test_operator_cross_source_pair_blocks_in_central_matcher():
    assert remains_return_count(FIRST["raw_text"]) == 252
    assert remains_return_count(SECOND["raw_text"]) == 252
    same, reason = repatriation_same_event(SECOND, FIRST)
    assert same, reason
    same, reason = event_fingerprint_same_event(SECOND, FIRST)
    assert same and "repatriation" in reason, reason


def test_minimal_published_ledger_row_does_not_require_source_url_or_source_time():
    ledger = {k: FIRST[k] for k in ("id", "channel_id", "source_id", "title", "raw_text", "final_text", "published_at")}
    assert event_fingerprint_same_event(SECOND, ledger)[0]


def test_national_item_does_not_pass_as_local_news_from_regional_source():
    ch = monitoring()
    assert "MONITORING_NONLOCAL_REPATRIATION" in civic_relevance_exclusion(ch, SECOND)
    assert "MONITORING_NONLOCAL_REPATRIATION" in live_now_exclusion(ch, SECOND)
    assert "MONITORING_NONLOCAL_REPATRIATION" in hard_editorial_reject(ch, SECOND, "Повернули тіла 252 військових.")
    assert any("MONITORING_NONLOCAL_REPATRIATION" in issue for issue in
               prepublish_quality_issues(ch, SECOND, "Повернули тіла 252 військових."))


def test_no_veto_without_opt_in_and_for_editorial():
    assert civic_relevance_exclusion(monitoring(opt_in=False), SECOND) == ""
    assert civic_relevance_exclusion(monitoring(mode=ChannelMode.EDITORIAL), SECOND) == ""


def test_local_return_of_fallen_servicemembers_is_preserved():
    item = dict(SECOND, title="У Запоріжжі родинам повернули тіла 252 полеглих військових.")
    item["raw_text"] = item["title"]
    assert civic_relevance_exclusion(monitoring(), item) == ""


def test_another_repatriation_count_is_not_same_event():
    separate = dict(SECOND, title="В Україну повернули тіла 253 загиблих військових", raw_text="В Україну повернули тіла 253 загиблих військових")
    assert not repatriation_same_event(separate, FIRST)[0]


def test_identification_or_family_handover_is_a_material_follow_up():
    update = dict(SECOND, raw_text=SECOND["raw_text"] + " Згодом ідентифікували 50 тіл.")
    assert not repatriation_same_event(update, FIRST)[0]


def test_repatriation_next_day_is_a_different_announcement():
    next_day = dict(SECOND, source_published_at="2026-10-23T13:17:07+03:00")
    assert not repatriation_same_event(next_day, FIRST)[0]


def test_ambiguous_or_missing_timestamps_cannot_block():
    undated = dict(SECOND, source_published_at="", published_at="", discovered_at="")
    assert not repatriation_same_event(undated, FIRST)[0]
    naive = dict(SECOND, source_published_at="2026-10-22T13:17:07", published_at="", discovered_at="")
    assert not repatriation_same_event(naive, FIRST)[0]


def test_same_source_not_cross_publisher_lane():
    same_source = dict(SECOND, source_id=FIRST["source_id"])
    assert not repatriation_same_event(same_source, FIRST)[0]


def test_non_remains_prisoner_exchange_not_confused_with_returned_bodies():
    exchange = dict(SECOND, title="В Україну повернули 252 військовополонених", raw_text="В Україну повернули 252 військовополонених")
    assert not repatriation_same_event(exchange, FIRST)[0]


def test_general_community_news_not_suppressed():
    item = dict(SECOND, title="У Запоріжжі відкрили нове укриття", raw_text="У Запоріжжі відкрили нове укриття")
    assert civic_relevance_exclusion(monitoring(), item) == ""
