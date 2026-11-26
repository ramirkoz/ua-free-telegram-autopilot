from telegram_autopilot.v2.storage import V2Store
from telegram_autopilot.v2.support_routes_2364 import reserve_support, MAX_HOURLY, MAX_DAILY
from telegram_autopilot.v2.ai_gateway import AIGateway
from telegram_autopilot.v2.semantic_dedupe import SemanticDedupeEngine
from telegram_autopilot.v2.ready_backlog import ReadyBacklogStore
from telegram_autopilot.evidence_pack import build_evidence_pack
from telegram_autopilot.v2.editorial_second_opinion_2320 import verified_second_opinion_2320
from test_v2_rc44_ready_backlog import _seed_ready
from test_2364_support_routes import setup
from telegram_autopilot.v2 import ai_gateway as gateway_mod
from telegram_autopilot.ai_router import Slot
from types import SimpleNamespace
import json


def test_groq_rate_paced_across_restart(tmp_path):
    db = tmp_path/'db.sqlite3'
    s=V2Store(db)
    assert reserve_support(s,'groq','article',now=100000)
    assert not reserve_support(V2Store(db),'groq','article2',now=100059)
    assert reserve_support(s,'nvidia','article2',now=100059)
    assert reserve_support(V2Store(db),'groq','article2',now=100060)


def test_daily_admission_ceiling_survives_restart(tmp_path):
    db=tmp_path/'db.sqlite3';s=V2Store(db)
    for i in range(MAX_DAILY):
        assert reserve_support(s,'nvidia','x',now=100000+i*200)
    assert not reserve_support(V2Store(db),'nvidia','x',now=124001)


def test_capped_provider_not_reserved_twice(monkeypatch):
    g,_,calls=setup(monkeypatch)
    monkeypatch.setattr(g,'_runtime_slots',lambda cfg:[Slot(1,'groq','qwen/qwen3.8-27b','Qwen'),Slot(2,'groq','openai/gpt-oss-120b','OSS'),Slot(3,'nvidia','nvidia/nemotron-3-ultra-550b-a55b','Ultra')])
    attempts=[]
    def admit(store,provider,prompt):
        attempts.append(provider);return provider=='nvidia'
    monkeypatch.setattr(gateway_mod,'reserve_support',admit)
    assert g.run('source',purpose='editorial_selector',validator=json.loads,max_output_tokens=220).provider=='nvidia'
    assert attempts==['groq','nvidia']
    assert len(calls)==1


def test_selector_contract_failure_demotes_only_exact_purpose(monkeypatch):
    g,_,_=setup(monkeypatch)
    bad=Slot(1,'openrouter','solar','solar');good=Slot(2,'openrouter','other','other')
    for _ in range(8): g._note_contract_outcome('editorial_selector','solar',ok=True)
    for _ in range(2): g._note_contract_outcome('editorial_selector','solar',ok=False,error=ValueError('EDITOR_2330_PUBLISH_WITHOUT_SOURCE_EVIDENCE'))
    assert g._order_by_contract_success([bad,good],'editorial_selector')==[good,bad]
    assert g._order_by_contract_success([bad,good],'writer')==[bad,good]
    g._note_contract_outcome('editorial_selector','solar',ok=True)
    assert g._order_by_contract_success([bad,good],'editorial_selector')==[bad,good]


def test_reader_contract_failure_is_not_a_reader_veto(monkeypatch):
    g,_,_=setup(monkeypatch)
    for _ in range(2):g._note_contract_outcome('reader_gate','x',ok=False,error=ValueError('READER_2359_MISSING_BOOLEAN'))
    assert g._contract_unreliable('reader_gate','x')
    assert not g._contract_unreliable('writer','x')


def test_startup_dedupe_skips_only_terminal_review(tmp_path,monkeypatch):
    s=ReadyBacklogStore(tmp_path/'db.sqlite3');_seed_ready(s,hours_old=1)
    s.update_article(1,blocked_by='QUALITY',last_error_code='QUALITY_RETRY_EXHAUSTED',next_retry_at='')
    e=SemanticDedupeEngine(s);calls=[]
    monkeypatch.setattr(e,'prepublish',lambda aid:(calls.append(aid),SimpleNamespace(relation='SINGLE'))[1])
    assert e.reconcile_ready_against_published()==0 and calls==[]
    assert s.get_article(1)['stage']=='READY'
    s.update_article(1,blocked_by='NONE',last_error_code='')
    e.reconcile_ready_against_published();assert calls==[1]


def test_selector_separates_excerpts_without_changing_evidence():
    article={'title':'Science','raw_text':'A first sentence contains real details. '+('A long background sentence with ordinary words. '*70)+'NASA measured a result of 45 km. More background.'}
    a=build_evidence_pack(article,char_budget=600)
    b=build_evidence_pack(article,char_budget=600,separate_passages=True)
    assert a.truncated and b.truncated
    assert a.text.split()==b.text.split()
    assert b.text.count('\n')>a.text.count('\n')
    assert verified_second_opinion_2320({'decision':'publish','source_quote':'NASA measured a result of 45 km.'},article)
    assert not verified_second_opinion_2320({'decision':'publish','source_quote':'NASA measured a result of 90 km.'},article)
