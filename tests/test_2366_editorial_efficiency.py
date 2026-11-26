import json
import pytest
from telegram_autopilot.v2.editorial_voice_2337 import newsroom_voice_2337
from telegram_autopilot.v2.selector_evidence_2366 import selector_evidence_2366, resolve_evidence_2366
from telegram_autopilot.v2.editorial_second_opinion_2320 import verified_second_opinion_2320
from telegram_autopilot.v2.numeric_schedule_2313 import schedule_rows_2366, schedule_row_guidance_2366
from telegram_autopilot.v2.ai_route_circuit_263 import RouteContractCircuit
from telegram_autopilot.v2.provider_api import ProviderAPIError
from telegram_autopilot.v2 import editorial_voice_2337 as voice
from telegram_autopilot.v2.ai_gateway import AIGateway

@pytest.mark.parametrize('role,block', [('science',voice._OWNER_SCIENCE_2345),('commercial',voice._OWNER_CREATIVE_2345),('monitoring',voice._OWNER_MONITORING_2345)])
@pytest.mark.parametrize('final',[True,False])
def test_compact_preserves_role_and_owner_specific_rules(role,block,final):
    old=newsroom_voice_2337(**{role:True},final=final)
    new=newsroom_voice_2337(**{role:True},final=final,compact=True)
    assert len(old)-len(new)>=1800
    assert block in new
    assert 'SOURCE' in new and 'Не вигадуй нових фактів' in new
    assert 'важливих дат, адрес, умов, контактів' in new
    if final: assert 'КОЖНЕ твердження з SOURCE' in new


def test_exact_source_evidence_ids_do_not_include_title_or_invented_quote():
    raw='Researchers measured a new gravitational effect in 500 observations. The result has an uncertainty interval.'
    options=selector_evidence_2366(raw, 'TITLE: An unrelated claim.\nSELECTED SOURCE PASSAGES:\n'+raw)
    assert options['Q1']=='Researchers measured a new gravitational effect in 500 observations.'
    item={'decision':'publish','source_quote':'Q1'}
    assert verified_second_opinion_2320(resolve_evidence_2366(item,options),{'raw_text':raw})
    assert not verified_second_opinion_2320(resolve_evidence_2366({'decision':'publish','source_quote':'Q99'},options),{'raw_text':raw})
    assert item['source_quote']=='Q1'
    assert selector_evidence_2366(raw,'TITLE: '+raw)=={}
    assert not verified_second_opinion_2320(resolve_evidence_2366({'decision':'publish','source_quote':'Q1'},options),{'raw_text':'another source'})


def test_explicit_schedule_rows_keep_times_and_groups():
    raw='Графік відключень на 26 листопада1.1: 00:00 – 02:00, 17:30 – 22:301.2: 13:00 – 18:00, 22:00 – 24:00'
    assert schedule_rows_2366(raw)==(('1.1','00:00 – 02:00, 17:30 – 22:30'),('1.2','13:00 – 18:00, 22:00 – 24:00'))
    assert '1.2: 13:00 – 18:00, 22:00 – 24:00' in schedule_row_guidance_2366(raw)
    assert not schedule_rows_2366(raw+'1.2: 01:00 – 02:00')
    assert not schedule_rows_2366(raw.replace('24:00','24:30'))
    assert not schedule_rows_2366(raw+' інша версія')


def test_empty_final_response_circuit_is_model_specific():
    x=RouteContractCircuit();e=ProviderAPIError('Provider returned an empty assistant response',kind='bad_response')
    assert not x.note_failure('openrouter','luna',e,now=100)
    assert x.note_failure('openrouter','luna',e,now=110)
    assert x.remaining('openrouter','luna',now=111)>0
    assert not x.remaining('openrouter','pro',now=111)
    assert x.remaining('openrouter','luna',now=711)==0


def test_copy_contract_demotion_is_not_fact_veto():
    g=object.__new__(AIGateway)
    for _ in range(2):g._note_contract_outcome('writer','luna',ok=False,error=ValueError('AI додав число, якого немає у джерелі'))
    assert not g._contract_unreliable('writer','luna')
    for _ in range(2):g._note_contract_outcome('writer','luna',ok=False,error=ValueError('Provider returned an empty assistant response'))
    assert g._contract_unreliable('writer','luna')
    assert not g._contract_unreliable('final_editor','luna')
