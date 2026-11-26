from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import pytest
from telegram_autopilot.v2.freshness_fence_241 import strict_runtime_source_rejection_2367 as fence
from telegram_autopilot.v2.editorial import validate_writer_output, prepublish_quality_issues, EditorialEngine
from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode, ChannelPolicy
from telegram_autopilot.v2.source_fact_integrity import non_overridable_quality_issues
from telegram_autopilot.v2.start_fence_2367 import retire_prestart_unattempted_2367
from test_2334_ready_buffer_preflight import _store, _queue, START, OLD, AFTER_START, NOW

def test_no_gap_recovery_all_roles():
    for hours in (0,24):
        assert fence('2026-11-16T08:50:00+02:00',START,'2026-11-16T08:45:00+02:00',now=NOW,rolling_window_hours=hours)=='SOURCE_PREDATES_RUNTIME_START'
        assert fence(AFTER_START,START,'',now=NOW,rolling_window_hours=hours)==''
        assert fence('',START,'',now=NOW,rolling_window_hours=hours)=='SOURCE_DATE_UNVERIFIED'

def test_start_archives_unsent_ready_and_queued_preserves_receipts(tmp_path):
    store=_store(tmp_path)
    queued=_queue(store,'oldqueued',OLD,OLD)
    ready=_queue(store,'oldready',OLD,OLD,cid=3)
    uncertain=_queue(store,'unknown',OLD,OLD,cid=3,journal=True)
    new=_queue(store,'new',AFTER_START,AFTER_START)
    published=_queue(store,'published',OLD,OLD)
    with store.connect() as con:
        con.execute("UPDATE articles SET stage='READY',decision='PUBLISH',final_text='prepared' WHERE id IN (?,?)",(ready,uncertain))
        con.execute("UPDATE articles SET stage='PUBLISHED',decision='PUBLISH',telegram_message_id='123' WHERE id=?",(published,))
    assert retire_prestart_unattempted_2367(store,START)==2
    assert retire_prestart_unattempted_2367(store,START)==0
    assert store.get_article(ready)['stage']=='ARCHIVED'
    assert store.get_article(queued)['stage']=='ARCHIVED'
    assert store.get_article(new)['stage']=='COLLECTED'
    assert store.get_article(published)['stage']=='PUBLISHED'
    assert store.get_article(uncertain)['stage']=='READY'
    assert store.delivery_journal(uncertain)['state']=='UNKNOWN'

def test_short_complete_dispatch_and_fact_guard():
    text='У Запоріжжі відновили рух мостом.'
    a={'id':1,'title':text,'raw_text':text,'source_url':'https://t.me/example/1','canonical_source_url':'https://t.me/example/1'}
    c=ChannelConfig(id=3,name='ГРОМАДИ',telegram_chat_id='@test',mode=ChannelMode.MONITORING,policy=ChannelPolicy(target_min_chars=500,target_max_chars=750))
    assert validate_writer_output(a,text,min_chars=500,max_chars=750,regional_dispatch=True)==text
    assert not non_overridable_quality_issues(c,a,text)
    assert not prepublish_quality_issues(c,a,text)
    with pytest.raises(ValueError):
        validate_writer_output(a,text,min_chars=500,max_chars=750)
    with pytest.raises(ValueError):
        validate_writer_output(a,'У Запоріжжі відновили рух 17 мостами.',min_chars=1,max_chars=750,regional_dispatch=True)
    with pytest.raises(ValueError):
        validate_writer_output(a,'У Запоріжжі відновили рух',min_chars=1,max_chars=750,regional_dispatch=True)
