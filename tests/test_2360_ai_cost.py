from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor

from telegram_autopilot.v2.ai_cost_2360 import (
    reserve_paid_attempt, review_receipt, save_review_receipt, compact_prompt,
    compact_style_memory, MAX_PAID_EDITORIAL_ATTEMPTS, MAX_PAID_TOTAL_ATTEMPTS,
)
from telegram_autopilot.v2.ai_economics_237 import ai_article_scope
from telegram_autopilot.v2.storage import V2Store
from telegram_autopilot.v2.polarity_verifier import verify_source_polarity
from telegram_autopilot.v2 import openrouter_catalog as catalog


def test_persistent_paid_admission_includes_failed_calls(tmp_path):
    path=tmp_path/'db.sqlite3'
    store=V2Store(path)
    for _ in range(MAX_PAID_EDITORIAL_ATTEMPTS):
        assert reserve_paid_attempt(store, 71)
    restarted=V2Store(path)
    assert not reserve_paid_attempt(restarted, 71)
    assert reserve_paid_attempt(restarted, 72)
    for _ in range(MAX_PAID_TOTAL_ATTEMPTS-MAX_PAID_EDITORIAL_ATTEMPTS):
        assert reserve_paid_attempt(restarted,71,editorial=False)
    assert not reserve_paid_attempt(restarted,71,editorial=False)


def test_actual_cost_blocks_more_calls(tmp_path):
    store=V2Store(tmp_path/'db.sqlite3')
    with ai_article_scope(1,71):
        store.record_ai_usage(provider='openrouter', model='test', purpose='writer',actual_openrouter_usd=.0101)
    assert not reserve_paid_attempt(store,71)
    assert reserve_paid_attempt(store,72)


def test_concurrent_reservation(tmp_path):
    store=V2Store(tmp_path/'db.sqlite3')
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(lambda _:reserve_paid_attempt(store,71), range(12)))
    assert sum(results)==MAX_PAID_EDITORIAL_ATTEMPTS


def test_exact_receipt_survives_restart_and_invalidates_changes(tmp_path):
    path=tmp_path/'db.sqlite3';store=V2Store(path)
    channel=SimpleNamespace(id=2,policy='p1')
    article={'id':71,'title':'original','raw_text':'original evidence','source_url':'https://example.org/a'}
    assert not review_receipt(store,channel,article,'body')
    save_review_receipt(store,channel,article,'body','validated')
    store=V2Store(path)
    assert review_receipt(store,channel,article,'body')=='validated'
    assert not review_receipt(store,channel,article,'body!')
    assert not review_receipt(store,channel,dict(article,raw_text='new evidence'),'body')
    assert not review_receipt(store,SimpleNamespace(id=2,policy='p2'),article,'body')
    assert not review_receipt(store,channel,dict(article,id=72),'body')


def test_prompt_compaction_retains_source_and_policy():
    line='Preserve every independently verifiable fact and caveat.'
    evidence='This exact source sentence repeats.\nThis exact source sentence repeats.'
    prompt=line+'\n'+line+'\nSOURCE:\n'+evidence
    assert compact_prompt(prompt)==line+'\nSOURCE:\n'+evidence
    assert compact_style_memory('header\n🔥1: complete first\n🔥2: another')=='header\n🔥1: complete first'


def test_joined_sentences_and_unrelated_negation():
    source='Жінка може боятися повертатися додому. А може роками не наважуватися розповісти про те, що переживає, бо не знає, кому довіритися і чи повірять їй.Насильство має різні форми й може траплятися в різних обставинах: удома, на роботі, у громадських місцях, в інтернеті.'
    final='Насильство може траплятися вдома, на роботі, у громадських місцях та в інтернеті. Жінка може боятися повертатися додому чи роками не наважуватися розповісти про пережите.'
    assert not verify_source_polarity(source,final,source_id='113881')
    assert verify_source_polarity('У селі немає електропостачання через пошкодження мережі.','У селі є електропостачання через пошкодження мережі.',source_id='true-flip')
    assert not verify_source_polarity('Громада не лише ремонтує дороги, а й відновлює освітлення вулиць.','Громада ремонтує дороги та відновлює освітлення вулиць.',source_id='additive')


def test_price_before_excess_context_within_quality_tier(monkeypatch):
    rows=(catalog.OpenRouterModel('vendor/expensive','a',.000002,.000003,1000000,4,False),catalog.OpenRouterModel('vendor/efficient','b',.000001,.000001,128000,4,False))
    monkeypatch.setattr(catalog,'model_catalog',lambda **kwargs:rows)
    ids=catalog.candidate_model_ids_for_task(purpose='writer',prompt_chars=6000,max_output_tokens=1100)
    assert ids[0]=='vendor/efficient'
