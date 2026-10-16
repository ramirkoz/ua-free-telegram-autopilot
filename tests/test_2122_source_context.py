from types import SimpleNamespace
from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode, ChannelPolicy
from telegram_autopilot.v2.editorial import hard_editorial_reject

def _check(text):
    channel=ChannelConfig(id=3,name="Communities",telegram_chat_id="@test",mode=ChannelMode.MONITORING,policy=ChannelPolicy(monitoring_source_policy="connected_original"))
    article=SimpleNamespace(raw_text=text,title=text,source_name="Local newsroom",source_url="https://t.me/news/123")
    return hard_editorial_reject(channel,article)

def test_banter_has_no_reportable_event():
    assert _check("🙈 розважаємось, як можемо")=="MONITORING_BANTER_NOT_NEWS"

def test_newsroom_factual_report_remains_eligible():
    assert not _check("У Запоріжжі відкрили новий центр соціальної підтримки для місцевих родин.")

def test_current_attack_message_has_no_verified_outcome():
    assert _check('РСЗВ криють Комишуваху/Юр’ївку') == 'MONITORING_ACTIVE_ATTACK_WARNING'
