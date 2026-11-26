from types import SimpleNamespace
from unittest.mock import Mock
import threading
import pytest
from telegram_autopilot.v2 import provider_api
from telegram_autopilot.v2.ai_gateway import AIGateway
from telegram_autopilot.v2.storage import V2Store
from telegram_autopilot.v2.domain import ProviderState

@pytest.mark.parametrize('provider,models', [
    ('groq', ['openai/gpt-oss-120b', 'qwen/qwen3.8-27b']),
    ('cloudflare', ['@cf/google/gemma-4-26b-a4b-it', '@cf/zai-org/glm-4.7-flash']),
])
def test_probe_all_exact_models_and_reasoning_budget(tmp_path, monkeypatch, provider, models):
    gateway = AIGateway(V2Store(tmp_path/'test.sqlite3'))
    cfg = SimpleNamespace()
    monkeypatch.setattr(gateway, '_configured', lambda p,c: True)
    monkeypatch.setattr(gateway, '_provider_slots', lambda p,c: [SimpleNamespace(provider=p,model=m) for m in models])
    monkeypatch.setattr(gateway, '_provider_call_lock', lambda p: threading.Lock())
    calls=[]
    def reply(slot,cfg,prompt,**kw):
        calls.append((slot.model,kw))
        return 'OK',slot.model,'test',5,2,7
    monkeypatch.setattr(gateway,'_call_slot',reply)
    result = gateway._probe_provider(provider,cfg)
    assert result.state == ProviderState.HEALTHY
    assert [m for m,_ in calls] == models
    assert all(k['max_output_tokens']==1024 and k['exact_model'] and k['timeout_seconds']==35 for _,k in calls)

@pytest.mark.parametrize('text,returned_model', [('analysis only','openai/gpt-oss-120b'),('OK','openai/gpt-oss-20b')])
def test_probe_never_false_healthy(tmp_path, monkeypatch, text, returned_model):
    g=AIGateway(V2Store(tmp_path/'test.sqlite3'))
    monkeypatch.setattr(g,'_configured',lambda p,c: True)
    monkeypatch.setattr(g,'_provider_slots',lambda p,c:[SimpleNamespace(provider=p,model='openai/gpt-oss-120b')])
    monkeypatch.setattr(g,'_provider_call_lock',lambda p:threading.Lock())
    monkeypatch.setattr(g,'_call_slot',lambda *a,**k:(text,returned_model,'test',0,0,0))
    assert g._probe_provider('groq',SimpleNamespace()).state != ProviderState.HEALTHY

def test_exact_groq_request_does_not_fallback(monkeypatch):
    calls=[]
    def fail(url,**kw):
        calls.append(kw['payload']['model'])
        raise provider_api.ProviderAPIError('unsupported',kind='model')
    monkeypatch.setattr(provider_api,'_request_json',fail)
    with pytest.raises(provider_api.ProviderAPIError):
        provider_api.openai_compatible_chat('groq', model='openai/gpt-oss-120b', api_key='test',prompt='OK', max_output_tokens=1024,timeout_seconds=35,exact_model=True)
    assert calls == ['openai/gpt-oss-120b']
