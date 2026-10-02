from __future__ import annotations

import json

from telegram_autopilot.v2.ai_gateway import AIResult
from telegram_autopilot.v2.editorial import EditorialEngine
from telegram_autopilot.v2.editorial_review import EditorialReviewService
from telegram_autopilot.v2.ready_backlog import ReadyBacklogStore
from telegram_autopilot.v2.storage import V2Store, now_iso


def _seed(store: V2Store) -> None:
    now = now_iso()
    with store.connect() as con:
        con.execute(
            """INSERT INTO channels(
                   id,name,telegram_chat_id,channel_mode,poll_interval_minutes,max_age_hours,
                   min_publish_interval_minutes,publish_24h,created_at,updated_at
               ) VALUES(1,'TEST','@test','editorial',15,24,60,0,?,?)""",
            (now, now),
        )
        con.execute(
            """INSERT INTO channel_policies(
                   channel_id,purpose,audience,selection_rules,rejection_rules,writing_rules,style_rules,
                   selector_extra_prompt,writer_extra_prompt,updated_at
               ) VALUES(1,'Tech','Readers','','','','','','',?)""",
            (now,),
        )
        con.execute("INSERT INTO sources(id,channel_id,kind,name,url,enabled,priority) VALUES(1,1,'rss','Source','https://example.com/feed',1,50)")


def _article(store: V2Store, external_id: str, *, stage: str='WRITTEN', decision: str='REJECT', error: str='') -> int:
    with store.connect() as con:
        cur = con.execute(
            """INSERT INTO articles(
                   channel_id,source_id,external_id,title,source_url,canonical_source_url,raw_text,
                   discovered_at,stage,decision,blocked_by,final_text,last_error_code,last_error_detail
               ) VALUES(1,1,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                external_id, 'Story', f'https://example.com/{external_id}', f'https://example.com/{external_id}',
                'Useful source facts', now_iso(), stage, decision, 'MEDIA' if error else 'NONE',
                'Готовий людський текст', error, 'технічний блокер' if error else '',
            ),
        )
        return int(cur.lastrowid)


def test_approved_material_stays_in_review_until_published(tmp_path):
    store = V2Store(tmp_path / 'db.sqlite3')
    _seed(store)
    review = EditorialReviewService(store)
    article_id = _article(store, 'approved')

    review.approve(article_id)
    ids = {x.article_id for x in review.candidates(limit=50)}
    assert article_id in ids

    store.update_article(article_id, blocked_by='MEDIA', last_error_code='MEDIA_REQUIRED', last_error_detail='Немає медіа')
    items = {x.article_id: x for x in review.candidates(limit=50)}
    assert article_id in items
    assert items[article_id].blocked_by == 'MEDIA'

    store.update_article(article_id, stage='PUBLISHED', published_at=now_iso())
    assert article_id not in {x.article_id for x in review.candidates(limit=50)}


def test_human_reject_is_terminal_and_media_recovery_does_not_resurrect(tmp_path):
    store = ReadyBacklogStore(tmp_path / 'db.sqlite3')
    _seed(store)
    review = EditorialReviewService(store)
    article_id = _article(store, 'reject', stage='ARCHIVED', decision='REJECT', error='MEDIA_REQUIRED')
    review.reject(article_id, 'Редактор сказав ні')

    assert store._recover_nonrequired_media_backlog() == 0
    row = store.get_article(article_id)
    assert row is not None
    assert row['stage'] == 'ARCHIVED'
    assert row['decision'] == 'REJECT'
    assert article_id not in {x.article_id for x in review.candidates(limit=50)}


class _OneShotGateway:
    def __init__(self):
        self.calls = []

    def run(self, prompt, **kwargs):
        self.calls.append(dict(kwargs))
        payload = {
            'decision': 'publish', 'fit_score': 90, 'reason': 'fit', 'angle': 'angle', 'topic_tags': ['ai'],
            'novelty': 80, 'consequence_or_insight': 80, 'mechanism': 80, 'reader_payoff': 80,
            'retellability': 80, 'concrete_stakes': 80, 'why_now': 80, 'curiosity_only': False,
            'commercial_mechanism': 80, 'consumer_behavior': 80, 'creative_execution': 80,
            'measurable_result': 80, 'strategic_transferability': 80, 'general_interest': 80,
            'culture_signal': 80, 'surprise_or_conflict': 80, 'consumer_relevance': 80,
        }
        raw = json.dumps(payload, ensure_ascii=False)
        validator = kwargs.get('validator')
        if validator:
            validator(raw)
        return AIResult(raw, 'gemini', 'gemini-3.5-flash', 'Gemini', ('gemini:gemini-3.5-flash',))


def test_editorial_fit_and_value_use_one_ai_call(tmp_path):
    store = V2Store(tmp_path / 'db.sqlite3')
    _seed(store)
    article_id = _article(store, 'combined', stage='COLLECTED', decision='PENDING')
    article = store.get_article(article_id)
    channel = store.get_channel(1)
    gateway = _OneShotGateway()
    engine = EditorialEngine(store, gateway)

    outcome = engine._select_editorial(channel, article)
    assert str(outcome.decision) == 'PUBLISH'
    assert len(gateway.calls) == 1
    assert gateway.calls[0]['purpose'] == 'editorial_selector'
    assert 'local' not in gateway.calls[0]['allowed_providers']


def test_reject_selector_does_not_require_value_metrics(tmp_path):
    store = V2Store(tmp_path / 'db.sqlite3')
    _seed(store)
    article_id = _article(store, 'reject-fast', stage='COLLECTED', decision='PENDING')
    article = store.get_article(article_id)
    channel = store.get_channel(1)

    class RejectGateway(_OneShotGateway):
        def run(self, prompt, **kwargs):
            self.calls.append(dict(kwargs))
            raw = json.dumps({'decision': 'reject', 'fit_score': 10, 'reason': 'не підходить'}, ensure_ascii=False)
            kwargs['validator'](raw)
            return AIResult(raw, 'gemini', 'gemini-3.5-flash', 'Gemini', ('gemini:gemini-3.5-flash',))

    gateway = RejectGateway()
    engine = EditorialEngine(store, gateway)
    outcome = engine._select_editorial(channel, article)
    assert str(outcome.decision) == 'REJECT'
    assert len(gateway.calls) == 1


def test_rc102_contract_module_installs_force_publish_and_human_override():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / 'telegram_autopilot' / 'v2'
    patch = (root / 'runtime_contracts.py').read_text(encoding='utf-8')
    review = (root / 'editorial_review.py').read_text(encoding='utf-8')
    assert 'publish_one(article_id, force=True)' in patch
    assert 'HUMAN_APPROVE_OVERRIDE' in patch
    assert 'APPROVED_NOT_PUBLISHED_' in patch
    assert "AND ea.action='reject'" in review
