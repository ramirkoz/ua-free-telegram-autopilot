from types import SimpleNamespace
from telegram_autopilot.v2.ai_cost_2360 import reserve_paid_attempt, prompt_shape_2363
from telegram_autopilot.v2.storage import V2Store
from telegram_autopilot.v2.cost_quality_232 import safe_format_candidate
from telegram_autopilot.v2.ai_economics_237 import ai_article_scope
from telegram_autopilot.v2.ai_gateway import AIGateway
from telegram_autopilot.v2 import ai_gateway as mod
from telegram_autopilot.ai_router import Slot
from telegram_autopilot.v2.domain import ProviderHealth


def test_phase_reserve_live_115642_115643(tmp_path):
    store=V2Store(tmp_path/'db.sqlite3')
    for article in (115642,115643):
        for _ in range(3):
            assert reserve_paid_attempt(store,article,editorial=False,purpose='monitoring_selector')
        for _ in range(3):
            assert reserve_paid_attempt(store,article,purpose='writer')
        assert not reserve_paid_attempt(store,article,purpose='writer')
        assert not reserve_paid_attempt(store,article,editorial=False,purpose='monitoring_selector')
        store=V2Store(store.path)
        assert reserve_paid_attempt(store,article,purpose='final_editor')
        assert not reserve_paid_attempt(store,article,purpose='final_editor')
        assert reserve_paid_attempt(store,article,purpose='reader_gate')
        assert not reserve_paid_attempt(store,article,purpose='reader_gate')
        with store.connect() as con:
            assert tuple(con.execute('SELECT attempts,editorial_attempts FROM ai_article_budget_2360 WHERE article_id=?',(article,)).fetchone())==(8,5)


def test_selector_cannot_consume_reserved_slots(tmp_path):
    store=V2Store(tmp_path/'db.sqlite3')
    for _ in range(5):
        assert reserve_paid_attempt(store,1,editorial=False,purpose='editorial_selector')
    assert not reserve_paid_attempt(store,1,editorial=False,purpose='editorial_selector')
    assert reserve_paid_attempt(store,1,purpose='writer')
    assert reserve_paid_attempt(store,1,purpose='final_editor')
    assert reserve_paid_attempt(store,1,purpose='reader_gate')


def test_actual_spend_threshold_still_blocks_reader(tmp_path):
    store=V2Store(tmp_path/'db.sqlite3')
    with ai_article_scope(3,42):
        store.record_ai_usage(provider='openrouter',model='x',purpose='writer',actual_openrouter_usd=.0101)
    assert not reserve_paid_attempt(store,42,purpose='reader_gate')


def test_selector_cache_exact_scope_and_validated_output(tmp_path,monkeypatch):
    store=V2Store(tmp_path/'db.sqlite3'); g=AIGateway(store)
    cfg=SimpleNamespace(ai_mode='openrouter'); slot=Slot(1,'openrouter','test/model','Test route')
    monkeypatch.setattr(mod,'load_secrets',lambda:cfg)
    monkeypatch.setattr(g,'_runtime_slots',lambda cfg:[])
    monkeypatch.setattr(g,'_openrouter_task_slots',lambda *a,**k:[slot])
    monkeypatch.setattr(g,'_configured',lambda p,c:True)
    monkeypatch.setattr(g,'_provider_blocked',lambda p:False)
    monkeypatch.setattr(g,'_model_blocked',lambda p,m:False)
    monkeypatch.setattr(g,'_openrouter_budget_status',lambda c:(True,''))
    monkeypatch.setattr(g,'_mark_success',lambda *a:None)
    monkeypatch.setattr(g,'_refresh_provider_summary',lambda p,c:ProviderHealth(provider=p))
    calls=[]; checks=[]
    def call(slot,cfg,prompt,**kw):
        calls.append(prompt);return 'approved',slot.model,slot.label,10,2,12
    monkeypatch.setattr(g,'_call_slot',call)
    def validate(text):
        assert text=='approved';checks.append(text)
    def run(prompt):
        return g.run(prompt,validator=validate,purpose='monitoring_selector')
    with ai_article_scope(3,42):
        assert run('same source and policy').text=='approved'
        assert run('same source and policy').label=='validated selector checkpoint'
        assert run('changed source and policy').label!='validated selector checkpoint'
    with ai_article_scope(3,43):
        run('same source and policy')
    assert len(calls)==3 and len(checks)==4


def test_paragraph_repair_only_whitespace_and_not_sentence_rewrite():
    p='Дослідники перевірили результати тривалого експерименту та оприлюднили новий звіт. Висновки команди підтвердили попередні оцінки та показали важливість подальшої роботи. '
    text=(p*3).strip()+'\n\nІнший абзац.'
    result=safe_format_candidate(text,ValueError('Readability QA: надто довгий абзац'))
    assert result and result.split()==text.split() and result.count('\n\n')==2
    assert not safe_format_candidate(text,ValueError('Readability QA: надто довгий абзац; є перевантажене речення понад 28 слів'))


def test_prompt_shape_does_not_export_text():
    raw='rules\nSOURCE:\nsecret source\nDRAFT:\nprivate draft'
    result=prompt_shape_2363(raw)
    assert result['purpose']=='final_editor' and result['source_section_chars']==len('secret source')
    assert all(isinstance(x,int) for k,x in result.items() if k!='purpose')


def test_retired_model_does_not_block_healthy_sibling(tmp_path,monkeypatch):
    from telegram_autopilot.v2.domain import AIModelHealth, ProviderState
    from telegram_autopilot.v2.storage import now_iso
    store=V2Store(tmp_path/'db.sqlite3'); g=AIGateway(store)
    retired='nvidia/nemotron-3-super-120b-a12b'; healthy='nvidia/nemotron-3-ultra-550b-a55b'
    store.set_ai_model_health(AIModelHealth(provider='nvidia',model=retired,state=ProviderState.MODEL_UNSUPPORTED,detail='HTTP 410: model reached end of life',updated_at=now_iso()))
    monkeypatch.setattr(g,'_configured',lambda p,c:True)
    monkeypatch.setattr(g,'_provider_slots',lambda p,c:[Slot(1,p,retired,'retired'),Slot(2,p,healthy,'healthy')])
    calls=[]
    def call(slot,cfg,prompt,**kw):
        calls.append(slot.model);return 'OK',slot.model,slot.label,5,2,7
    monkeypatch.setattr(g,'_call_slot',call)
    assert g._probe_provider('nvidia',SimpleNamespace()).state==ProviderState.HEALTHY
    assert calls==[healthy]
    assert g._model_health_map()[('nvidia',retired)].state==ProviderState.MODEL_UNSUPPORTED


def test_final_reader_veto_terminal_not_overridden(monkeypatch):
    import pytest
    from test_2319_operator_editorial_router import _gateway
    from telegram_autopilot.v2.ai_gateway import GatewayExhausted
    g,_=_gateway(monkeypatch); calls=[]
    def call(slot,cfg,prompt,**kw):
        calls.append(slot.model)
        return ('REJECT_READER_2360' if len(calls)==1 else 'accepted',slot.model,slot.label,3,2,5)
    monkeypatch.setattr(g,'_call_slot',call)
    def validate(text):
        if text=='REJECT_READER_2360':
            raise ValueError('REJECT_READER_2360: source lacks broad reader value')
    with pytest.raises(GatewayExhausted,match='REJECT_READER_2360'):
        g.run('source',purpose='final_editor',validator=validate)
    assert len(calls)==1
