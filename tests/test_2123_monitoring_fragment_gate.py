from types import SimpleNamespace

from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode, ChannelPolicy
from telegram_autopilot.v2.editorial import monitoring_fragment_quality_issues, prepublish_quality_issues


def _channel():
    return ChannelConfig(
        id=3, name="ЗАПОРІЖЖЯ | ГРОМАДИ", telegram_chat_id="@test",
        mode=ChannelMode.MONITORING,
        policy=ChannelPolicy(monitoring_source_policy="connected_original"),
    )


def _article():
    source = (
        "На греблі в Запоріжжі сталася ДТП. Рух транспорту ускладнений. "
        "Водіям радять бути уважними та враховувати затримки."
    )
    return SimpleNamespace(
        title="ДТП на греблі", raw_text=source,
        source_name="ЗАПОРІЖЖЯ.ІНФО", source_url="https://example.com/local-report",
    )


def test_operator_traffic_post_with_damaged_fragment_is_blocked():
    final_text = (
        "🚨 На греблі в Запоріжжі сталася ДТП.\n\n"
        "Рух дуже ускладнений. Також проблеми на мостах тех.\n\n"
        "Будьте обережні на дорозі."
    )
    assert "MONITORING_BROKEN_SENTENCE_TAIL" in prepublish_quality_issues(
        _channel(), _article(), final_text
    )


def test_dangling_preposition_or_relative_pronoun_is_blocked():
    for text in (
        "На мостах проблеми через те, що",
        "На ділянці дороги затримка через ремонт на",
        "Рух ускладнений на мостах тих.",
    ):
        assert monitoring_fragment_quality_issues(text) == (
            "MONITORING_BROKEN_SENTENCE_TAIL",
        )


def test_valid_short_traffic_report_and_source_footer_survive():
    assert not monitoring_fragment_quality_issues(
        "У Запоріжжі на греблі сталася ДТП. Рух ускладнений. "
        "Водіїв просять враховувати затримки.\nЧитати у «ЗАПОРІЖЖЯ.ІНФО»"
    )


def test_factual_local_reporting_does_not_trigger_fragment_gate():
    assert not monitoring_fragment_quality_issues(
        "У Запоріжжі відкрили новий центр допомоги. "
        "Він працюватиме для родин із дітьми."
    )
