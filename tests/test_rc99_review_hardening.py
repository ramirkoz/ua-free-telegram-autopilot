from __future__ import annotations

import threading
from types import SimpleNamespace

from telegram_autopilot.network import NetworkError
from telegram_autopilot.v2.monitoring_live_now import live_now_exclusion
from telegram_autopilot.v2.publisher import _strip_all_publication_links


def test_network_error_tracks_pre_send_vs_unknown_outcome():
    assert NetworkError("dns").request_sent is False
    assert NetworkError("read", request_sent=True).request_sent is True


def _monitoring_channel():
    return SimpleNamespace(
        mode=__import__("telegram_autopilot.v2.domain", fromlist=["ChannelMode"]).ChannelMode.MONITORING,
        policy=SimpleNamespace(rejection_rules="[LIVE_NOW_RC96]"),
    )


def test_monitoring_rejects_bare_warning_without_inventing_context():
    reason = live_now_exclusion(_monitoring_channel(), {"title": "ЗАПОРІЖЖЯ ІНФО", "raw_text": "❗ Новомиколаївка, уважно"})
    assert "Недостатньо контексту" in reason


def test_monitoring_allows_settled_aftermath():
    text = "Внаслідок нічної атаки зафіксовано влучання в район міста. Пошкоджено 12 будинків, поранено 3 людей. Пожежу ліквідовано."
    assert live_now_exclusion(_monitoring_channel(), {"title": "", "raw_text": text}) == ""


def test_monitoring_does_not_treat_sport_attack_as_war_alert():
    text = "Динамо атакували ворота суперника й перемогли 2:0."
    assert live_now_exclusion(_monitoring_channel(), {"title": "", "raw_text": text}) == ""


def test_strip_body_links_preserves_sentence_punctuation():
    assert _strip_all_publication_links("Деталі (https://example.com/a/b).") == "Деталі ."
    assert _strip_all_publication_links("Ціна 5 грн (https://shop.ua/p?id=1)!") == "Ціна 5 грн !"


def test_advanced_update_discovery_is_threaded_source_contract():
    import inspect
    from telegram_autopilot.v2.advanced_update_coordinator import AdvancedUpdateCoordinator
    source = inspect.getsource(AdvancedUpdateCoordinator.poll)
    assert "V2-Update-Discovery" in source
    assert "threading.Thread" in source
    assert "900000" in inspect.getsource(__import__("telegram_autopilot.v2.update_coordinator", fromlist=["UpdateCoordinator"]).UpdateCoordinator._schedule)
