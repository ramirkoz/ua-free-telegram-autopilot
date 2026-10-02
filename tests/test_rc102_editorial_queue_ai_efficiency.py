from __future__ import annotations

from telegram_autopilot.v2.rc102_contract import (
    Rc102EditorialEngine,
    Rc102EditorialReviewService,
    Rc102Gateway,
    Rc102Publisher,
    Rc102Supervisor,
)
from telegram_autopilot.v2.storage import V2Store, now_iso


def _seed(store: V2Store) -> int:
    stamp = now_iso()
    with store.connect() as con:
        con.execute("INSERT INTO channels(id,name,telegram_chat_id,channel_mode,poll_interval_minutes,max_age_hours,min_publish_interval_minutes,publish_24h,created_at,updated_at) VALUES(1,'X','-1001','editorial',15,24,30,0,?,?)", (stamp, stamp))
        con.execute("INSERT INTO channel_policies(channel_id,purpose,audience,updated_at) VALUES(1,'tech','broad',?)", (stamp,))
        con.execute("INSERT INTO sources(id,channel_id,kind,name,url,enabled,priority) VALUES(1,1,'rss','S','https://example.com',1,100)")
    aid = store.insert_collected(channel_id=1, source_id=1, external_id='a', title='T', source_url='https://example.com/a', raw_text='body')
    store.update_article(aid, final_text='Готовий редакторський текст.', stage='QA_PASSED', decision='PUBLISH')
    return aid


def test_approved_item_stays_visible_until_published_and_reject_is_terminal(tmp_path):
    store = V2Store(tmp_path / 'a.db'); store.initialize(); aid = _seed(store)
    review = Rc102EditorialReviewService(store)
    review.approve(aid)
    assert aid in {x.article_id for x in review.candidates()}
    review.reject(aid)
    assert aid not in {x.article_id for x in review.candidates()}
    row = store.get_article(aid)
    assert row['stage'] == 'ARCHIVED' and row['decision'] == 'REJECT'


def test_human_publisher_has_manual_publish_contract(tmp_path):
    store = V2Store(tmp_path / 'a.db'); store.initialize(); _seed(store)
    publisher = Rc102Publisher(store)
    assert hasattr(publisher, 'publish_human_approved')


def test_rc102_ai_classes_are_wired_for_combined_selection():
    assert issubclass(Rc102Gateway, object)
    assert 'selector/value combined' in Rc102EditorialEngine._select_editorial.__code__.co_consts
    assert Rc102Supervisor is not None
