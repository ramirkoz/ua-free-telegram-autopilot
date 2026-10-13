from datetime import datetime, timedelta, timezone

from telegram_autopilot.v2.ingest import _stale_at_ingest

NOW = datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc)


def test_channel_age_window_is_authoritative():
    old = (NOW - timedelta(hours=48)).isoformat()
    assert _stale_at_ingest(old, 24, now=NOW)
    assert not _stale_at_ingest(old, 72, now=NOW)


def test_recent_timezone_and_boundary_survive():
    recent = (NOW - timedelta(hours=23)).astimezone(timezone(timedelta(hours=3))).isoformat()
    assert not _stale_at_ingest(recent, 24, now=NOW)
    assert not _stale_at_ingest(NOW.isoformat(), 24, now=NOW)


def test_uncertain_date_must_not_create_false_rejections():
    for date in ('', None, 'not-a-date', '2026-10-12 10:00:00'):
        assert not _stale_at_ingest(date, 24, now=NOW)


def test_historical_dated_news_filtered():
    assert _stale_at_ingest('2024-10-13T13:00:00+03:00', 24, now=NOW)
    assert _stale_at_ingest('2022-02-01T10:00:00Z', 24, now=NOW)


def test_future_dated_items_are_not_discarded_as_old():
    assert not _stale_at_ingest((NOW + timedelta(minutes=15)).isoformat(), 24, now=NOW)


def test_rss_rfc2822_dates_are_filtered():
    assert _stale_at_ingest("Wed, 26 Aug 2026 23:08:00 GMT", 24, now=NOW)
    assert not _stale_at_ingest("Tue, 13 Oct 2026 09:30:00 +0000", 24, now=NOW)


def test_old_new_item_skipped_before_database_and_ai(tmp_path, monkeypatch):
    from telegram_autopilot.models import CollectedArticle
    from telegram_autopilot.v2.ingest import IngestService
    from telegram_autopilot.v2.storage import V2Store, now_iso
    import telegram_autopilot.v2.ingest as ingest
    store = V2Store(tmp_path / 'age-integration.sqlite3')
    stamp = now_iso()
    with store.connect() as con:
        con.execute('INSERT INTO channels(id,name,telegram_chat_id,created_at,updated_at) VALUES(1,?,?,?,?)', ('Test', '@test', stamp, stamp))
        con.execute('INSERT INTO sources(id,channel_id,kind,name,url) VALUES(1,1,?,?,?)', ('rss', 'Test RSS', 'https://example.com/rss'))
    monkeypatch.setattr(ingest, 'collect', lambda source: [
        CollectedArticle('old-guid', 'Old item', 'https://example.com/old', 'Historic story', 'Wed, 26 Aug 2026 23:08:00 GMT'),
        CollectedArticle('fresh-guid', 'Fresh item', 'https://example.com/fresh', 'Recent news', datetime.now(timezone.utc).isoformat()),
    ])
    result = IngestService(store).collect_channel(1)
    assert result['seen'] == 2
    assert result['added'] == 1
    assert result['stale_filtered'] == 1
    with store.connect() as con:
        assert con.execute('SELECT COUNT(*) FROM articles').fetchone()[0] == 1
        assert con.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] == 1


def test_old_known_item_can_still_refresh_media(tmp_path, monkeypatch):
    from telegram_autopilot.models import CollectedArticle
    from telegram_autopilot.v2.ingest import IngestService
    from telegram_autopilot.v2.storage import V2Store, now_iso
    import telegram_autopilot.v2.ingest as ingest
    store = V2Store(tmp_path / 'age-refresh.sqlite3')
    stamp = now_iso()
    with store.connect() as con:
        con.execute('INSERT INTO channels(id,name,telegram_chat_id,created_at,updated_at) VALUES(1,?,?,?,?)', ('Test', '@test', stamp, stamp))
        con.execute('INSERT INTO sources(id,channel_id,kind,name,url) VALUES(1,1,?,?,?)', ('rss', 'Test RSS', 'https://example.com/rss'))
    article = store.insert_collected(channel_id=1, source_id=1, external_id='known', title='Known', source_url='https://example.com/known', raw_text='Story', source_published_at='Wed, 26 Aug 2026 23:08:00 GMT')
    monkeypatch.setattr(ingest, 'collect', lambda source: [CollectedArticle(
        'known', 'Known', 'https://example.com/known', 'Story', 'Wed, 26 Aug 2026 23:08:00 GMT', ['https://example.com/photo.jpg'],
    )])
    result = IngestService(store).collect_channel(1)
    assert result['stale_filtered'] == 0
    assert result['added'] == 0
    assert 'photo.jpg' in str(store.get_article(article)['media_json'])
