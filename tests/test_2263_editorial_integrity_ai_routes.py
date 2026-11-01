"""2.2.63 LIVE source copy, age agreement and AI budget regressions."""
from types import SimpleNamespace
from datetime import datetime
import inspect

import pytest
from telegram_autopilot.v2.domain import ChannelMode
from telegram_autopilot.v2.monitoring_news_integrity_263 import (
    monitoring_source_promo_reason, monitoring_unverified_teaser_reason,
    monitoring_copied_cta_issue, MONITORING_NEWS_INTEGRITY_RULE_263,
)
from telegram_autopilot.v2.editorial_reader_contract_252 import source_completeness_issue
from telegram_autopilot.v2.editorial import (
    EditorialEngine, _source_body_policy_issues, hard_editorial_reject,
    prepublish_quality_issues,
)
from telegram_autopilot.ukrainian_quality import apply_safe_ukrainian_fixes, final_language_blockers
from telegram_autopilot.v2.provider_api import ProviderAPIError
from telegram_autopilot.v2.ai_route_circuit_263 import RouteContractCircuit
from telegram_autopilot.v2.ai_gateway import AIGateway


def _monitor():
    return SimpleNamespace(mode=ChannelMode.MONITORING,id=3,
        policy=SimpleNamespace(rejection_rules="[LIVE_NOW_RC96]", monitoring_denied_origins="",
            monitoring_source_policy="connected_original"))


LIVE_PROMO = "👻 👻 Уявили Запоріжжя в стилі Гелловін-сторі Святкуєте? 💀 Діліться світлинами 👻 Ми в 📲WhatsApp 📲Instagram📲TikTok📲 Threads👻 БУ!"
LIVE_COMPLAINT = (
    "Отакий сюрприз отримали при замовленні в IQ pizza у Запоріжжі. "
    "Ось що пишуть запорожці: Замовлення не було готове. "
    "Вдома побачили такий «комплімент від шефа». Дуже розчаровані."
)


def test_live_social_promo_is_rejected_from_source_before_ai():
    a={"raw_text":LIVE_PROMO,"title":"Гелловін","source_name":"Сторонній канал"}
    assert monitoring_source_promo_reason(a)=="MONITORING_SOURCE_CHANNEL_SELF_PROMO_263"
    assert hard_editorial_reject(_monitor(),a)=="MONITORING_SOURCE_CHANNEL_SELF_PROMO_263"


@pytest.mark.parametrize("bad",[
    "Святкуєте Гелловін? Діліться світлинами Запоріжжя. Ми є у WhatsApp, Instagram, TikTok і Threads.",
    "Проєкт розповів про міські легенди. Гортайте картки, щоб прочитати.",
    "Міські легенди Запоріжжя. Діліться історіями в коментарях.",
    "Відкрилася виставка. Підписуйтеся на наш канал.",
])
def test_external_channel_cta_never_survives_final_gate(bad):
    assert monitoring_copied_cta_issue(bad)
    p=_source_body_policy_issues(_monitor(),{"raw_text":"У Запоріжжі відбулася виставка. Показали міські легенди."},bad)
    assert any("MONITORING_COPIED_CHANNEL_CTA_263" in item for item in p)


def test_civic_announcement_and_actionable_address_not_rejected():
    a={"raw_text":("У Запоріжжі відкрили чотири пункти гарячого харчування. "
         "Адреси оприлюднили для жителів міста. Ми також є у WhatsApp і Telegram."),
       "title":"Пункти харчування"}
    assert not monitoring_source_promo_reason(a)
    assert not monitoring_copied_cta_issue(
        "У Запоріжжі відкрили чотири пункти гарячого харчування. "
        "За адресою вулиця Перемоги, 12 пункт працює щодня."
    )
    assert not monitoring_copied_cta_issue(
        "Офіційне управління просить повідомляти про небезпечні предмети за номером 102."
    )


def test_live_87338_unverified_photo_complaint_fails_without_inventing_object():
    a={"raw_text":LIVE_COMPLAINT,"title":"Скарга на доставку"}
    assert monitoring_unverified_teaser_reason(a)=="MONITORING_UNVERIFIED_COMPLAINT_TEASER_263"
    assert "UNVERIFIED_COMPLAINT" in source_completeness_issue(a)


def test_verified_official_reputational_event_is_not_banned():
    a={"raw_text":"Держпродспоживслужба перевірила кафе та оприлюднила акт. Виявлено конкретні порушення.",
       "title":"Перевірка закладу"}
    assert not monitoring_unverified_teaser_reason(a)
    assert not source_completeness_issue(a)


def test_live_87860_ages_fixed_without_changing_numbers_or_science_facts():
    original="У дослідженні 210 учасників 11–18 рік розподілили на дві групи. Вправи тривали 3 місяці."
    result=apply_safe_ukrainian_fixes(original)
    assert result=="У дослідженні 210 учасників віком від 11 до 18 років розподілили на дві групи. Вправи тривали 3 місяці."
    assert final_language_blockers(original)
    assert not final_language_blockers(result)
    assert apply_safe_ukrainian_fixes("Програма тривала 11–18 рік.")=="Програма тривала 11–18 рік."


def test_ai_reasoning_only_circuit_is_model_scoped_expires_and_resets():
    x=RouteContractCircuit()
    err=ProviderAPIError("Provider returned reasoning but no final content; completion budget/format is incompatible",
                         kind="bad_response")
    assert not x.note_failure("openrouter","inclusionai/ling-3.0-flash",err,now=100)
    assert not x.remaining("openrouter","inclusionai/ling-3.0-flash",now=101)
    assert x.note_failure("openrouter","inclusionai/ling-3.0-flash",err,now=120)
    assert x.remaining("openrouter","inclusionai/ling-3.0-flash",now=121)>0
    assert x.remaining("openrouter","mistralai/mistral-nemo",now=121)==0
    assert x.remaining("gemini","inclusionai/ling-3.0-flash",now=121)==0
    assert x.remaining("openrouter","inclusionai/ling-3.0-flash",now=721)==0
    x.clear("openrouter","inclusionai/ling-3.0-flash")
    assert not x.note_failure("openrouter","inclusionai/ling-3.0-flash",err,now=722)


def test_local_timeout_circuit_only_after_two_real_failures():
    x=RouteContractCircuit()
    err=ProviderAPIError("Ollama не завершила локальне AI-завдання за 120 секунд.",kind="timeout")
    assert not x.note_failure("local","local-model",err,now=100)
    assert x.note_failure("local","local-model",err,now=130)
    assert 850<x.remaining("local","local-model",now=131)<901
    assert not x.note_failure("openrouter","a",ProviderAPIError("HTTP 429",kind="temporary"),now=132)


def test_runtime_uses_existing_gate_in_writer_final_and_prepublish_without_extra_ai():
    write=inspect.getsource(EditorialEngine.write)
    final=inspect.getsource(EditorialEngine._final_edit)
    before=inspect.getsource(prepublish_quality_issues)
    gateway=inspect.getsource(AIGateway.run)
    assert "{MONITORING_NEWS_INTEGRITY_RULE_263}" in write
    assert "{MONITORING_NEWS_INTEGRITY_RULE_263}" in final
    assert "_source_body_policy_issues(channel, article, value)" in before
    assert "self._route_circuit.remaining" in gateway
    assert "self._route_circuit.note_failure" in gateway
    assert "self._route_circuit.clear" in gateway
    assert "не повторюй" in MONITORING_NEWS_INTEGRITY_RULE_263.casefold()
