"""New routing contract; never send actual API requests."""
import json
import pytest
from telegram_autopilot.ai_router import Slot
from telegram_autopilot.v2 import ai_gateway as mod
from telegram_autopilot.v2.ai_gateway import GatewayExhausted
from telegram_autopilot.v2.storage import V2Store
from telegram_autopilot.v2.support_routes_2364 import reserve_support, MAX_HOURLY, MAX_PROMPT_BYTES
from test_2319_operator_editorial_router import _gateway


def setup(monkeypatch, budget=True, mode='openrouter'):
    g, usage = _gateway(monkeypatch, mode=mode, budget=budget)
    monkeypatch.setattr(g, '_runtime_slots', lambda cfg: [
        Slot(1, 'groq', 'qwen/qwen3.8-27b', 'Qwen'),
        Slot(2, 'nvidia', 'nvidia/nemotron-3-ultra-550b-a55b', 'Ultra'),
        Slot(3, 'cloudflare', '@cf/google/gemma-4-26b-a4b-it', 'Excluded Gemma')])
    monkeypatch.setattr(mod, 'reserve_support', lambda *a: True)
    calls=[]
    def generate(slot, cfg, prompt, **kw):
        calls.append((slot.provider, kw))
        from telegram_autopilot.v2.support_routes_2364 import _VALUE_KEYS, _COMMERCIAL_KEYS
        body = dict.fromkeys(_VALUE_KEYS+_COMMERCIAL_KEYS, 50)
        body.update(decision='reject', reason='Конкретний матеріал не містить нової інформації.', event_type='local_news', included=False, excluded=True, settled=True, curiosity_only=False, shareable_to_friend=False, product_only=False)
        return json.dumps(body), slot.model, slot.label, 10, 2, 12
    monkeypatch.setattr(g, '_call_slot', generate)
    return g, usage, calls

@pytest.mark.parametrize('purpose', ['editorial_selector','monitoring_selector','value_gate','commercial_value_gate'])
def test_validated_support_uses_direct_even_with_paid_available(monkeypatch, purpose):
    g, usage, calls = setup(monkeypatch)
    assert g.run('SOURCE', purpose=purpose, validator=json.loads, max_output_tokens=220).provider == 'groq'
    assert len(calls) == 1
    assert calls[0][1]['exact_model'] and calls[0][1]['single_request']
    assert usage[0]['purpose'] == purpose

@pytest.mark.parametrize('purpose', ['writer','final_editor','rewrite','complex_rewrite','content','reader_gate','unrecognized'])
@pytest.mark.parametrize('mode', ['openrouter','codex'])
def test_non_support_is_paid_only(monkeypatch,purpose,mode):
    g, _, calls=setup(monkeypatch, mode=mode)
    assert g.run('SOURCE', purpose=purpose, validator=json.loads,max_output_tokens=220).provider == 'openrouter'
    assert [p for p,_ in calls]==['openrouter']

@pytest.mark.parametrize('purpose', ['writer','final_editor','rewrite','content','reader_gate'])
def test_no_direct_text_when_paid_budget_exhausted(monkeypatch,purpose):
    g, _, calls=setup(monkeypatch,budget=False)
    with pytest.raises(GatewayExhausted):
        g.run('SOURCE',purpose=purpose,validator=json.loads,max_output_tokens=220)
    assert calls==[]

@pytest.mark.parametrize('reason',['limit','invalid','large','no_validator'])
def test_fallback_to_paid(monkeypatch,reason):
    g,_,calls=setup(monkeypatch)
    validator=json.loads
    prompt='SOURCE'
    if reason=='limit':monkeypatch.setattr(mod,'reserve_support',lambda *a:False)
    elif reason=='large':prompt='x'*(MAX_PROMPT_BYTES+1)
    elif reason=='no_validator':validator=None
    else:
        original=g._call_slot
        def bad(slot,cfg,prompt,**kw):
            row=original(slot,cfg,prompt,**kw)
            return ('INVALID',*row[1:]) if slot.provider=='groq' else row
        monkeypatch.setattr(g,'_call_slot',bad)
    assert g.run(prompt,purpose='editorial_selector',validator=validator,max_output_tokens=220).provider=='openrouter'
    assert [p for p,_ in calls]==(['groq','openrouter'] if reason=='invalid' else ['openrouter'])


def test_direct_support_still_available_with_paid_budget_exhausted(monkeypatch):
    g,_,calls=setup(monkeypatch,budget=False)
    assert g.run('SOURCE',purpose='monitoring_selector',validator=json.loads,max_output_tokens=220).provider=='groq'
    assert len(calls)==1


def test_direct_limits_are_persistent_and_atomic(tmp_path):
    path=tmp_path/'db.sqlite3';store=V2Store(path)
    for i in range(MAX_HOURLY): assert reserve_support(store,'nvidia','source',now=100000+i)
    assert not reserve_support(V2Store(path),'nvidia','source',now=100030)
    assert reserve_support(store,'groq','source',now=100030)
    assert reserve_support(store,'nvidia','source',now=103700)
    assert not reserve_support(store,'groq','x'*(MAX_PROMPT_BYTES+1),now=103701)


def test_single_request_disables_hidden_groq_retry(monkeypatch):
    from telegram_autopilot.v2 import provider_api as api
    calls=[]
    def request(*args,**kw):
        calls.append(kw)
        raise api.ProviderAPIError('invalid response',kind='validation')
    monkeypatch.setattr(api,'_request_json',request)
    with pytest.raises(api.ProviderAPIError):
        api.openai_compatible_chat('groq',model='qwen/qwen3.8-27b',api_key='test',prompt='SOURCE',max_output_tokens=220,timeout_seconds=5,json_mode=True,exact_model=True,single_request=True)
    assert len(calls)==1 and calls[0]['single_request']


def test_support_missing_scores_are_not_silently_zeroed():
    from telegram_autopilot.v2.support_routes_2364 import validate_support_response
    with pytest.raises(ValueError):
        validate_support_response('{"reason":"Змістовна причина"}', 'value_gate')
    with pytest.raises(ValueError):
        validate_support_response('{"decision":"reject","reason":"коротко"}', 'editorial_selector')
