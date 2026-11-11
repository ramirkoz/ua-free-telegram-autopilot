"""2.3.27: one-shot operator-approved RSS portfolio, without historic replay.

All 31 channel/feed assignments are installed on *the same startup* after the
legacy source migrations. Topic-only Telegram references are stored separately
from `sources`, so they can never accidentally enter the publication pipeline.
No network calls, deletion of source history, channel policy edits, or changes
to Telegram receipts occur here.
"""
from __future__ import annotations

import json
from urllib.parse import urlsplit
from typing import Any

from .loghub import event
from .storage import now_iso

VERSION = '2.3.27'
MARKER = 'editorial_source_portfolio_237_channel_'
HINT_MARKER = 'editorial_topic_hints_237_channel_'

SCIENCE_RSS: tuple[tuple[str, str, int], ...] = (
    ('Interesting Engineering','https://interestingengineering.com/feed',10),
    ('Futurism','https://futurism.com/feed',11),
    ('Live Science','https://www.livescience.com/feeds/all',12),
    ('ZME Science','https://www.zmescience.com/feed/',13),
    ('Digital Trends','https://www.digitaltrends.com/feed/',14),
    ('404 Media','https://www.404media.co/rss/',15),
    ('The Robot Report','https://www.therobotreport.com/feed/',16),
    ('Popular Mechanics','https://www.popularmechanics.com/rss/all.xml/',17),
    ('Smithsonian Smart News','https://www.smithsonianmag.com/rss/smart-news/',18),
    ('Gizmodo','https://gizmodo.com/feed',25),
    ('BGR','https://bgr.com/feed/',26),
    ('SCMP Tech','https://www.scmp.com/rss/36/feed',27),
    ('Electrek','https://electrek.co/feed/',28),
    ('9to5Mac','https://9to5mac.com/feed/',29),
    ('PetaPixel','https://petapixel.com/feed/',30),
)

CREATIVE_RSS: tuple[tuple[str, str, int], ...] = (
    ('Muse by Clio','https://musebycl.io/rss.xml',10),
    ('Creative Review','https://www.creativereview.co.uk/feed/',11),
    ('Dexerto','https://www.dexerto.com/feed/',12),
    ('Hypebeast','https://hypebeast.com/feed',13),
    ('Brand Eating','https://www.brandeating.com/feeds/posts/default',14),
    ('The Takeout','https://www.thetakeout.com/rss',15),
    ('Study Finds','https://studyfinds.org/feed/',16),
    ('PsyPost','https://www.psypost.org/feed/',17),
    ('UPI Odd News','https://rss.upi.com/news/odd_news.rss',18),
    ('SoraNews24','https://soranews24.com/feed/',19),
    ('Carscoops','https://www.carscoops.com/feed/',20),
    ('Fast Company','https://www.fastcompany.com/latest/rss',27),
    ('designboom','https://www.designboom.com/feed/',28),
    ('Bored Panda','https://www.boredpanda.com/feed/',29),
    ('Smithsonian Smart News','https://www.smithsonianmag.com/rss/smart-news/',30),
    ('ZME Science','https://www.zmescience.com/feed/',31),
)

# Only discovery/reference; NEVER represented as a publication source.
TOPIC_HINTS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ('technology','https://t.me/technology',('science','creative')),
    ('futurism','https://t.me/futurism',('science',)),
    ('science','https://t.me/science',('science','creative')),
    ('viral','https://t.me/viral',('creative',)),
    ('rockstargames','https://t.me/rockstargames',('creative',)),
    ('thehackernews','https://t.me/thehackernews',('science',)),
)


def canonical_feed(url: str) -> str:
    try:
        parsed = urlsplit(str(url or '').strip())
        hostname = (parsed.hostname or '').casefold().removeprefix('www.')
        if parsed.scheme not in {'http', 'https'} or not hostname:
            return ''
        # Retain path case in identity to avoid merging legitimately distinct feeds.
        return f'{hostname}{parsed.path.rstrip("/")}{"?"+parsed.query if parsed.query else ""}'
    except (ValueError, TypeError):
        return ''


def _canonical_role(channel: Any) -> str:
    if str(channel['channel_mode']) != 'editorial':
        return ''
    profile = str(channel['editorial_runtime_profile'] or '').casefold()
    if profile == 'commercial_editorial':
        return 'creative'
    # The scientific dedupe profile is part of the existing operator identity.
    if (str(channel['dedupe_profile'] or '').casefold() == 'scientific_news'
            or str(channel['name'] or '').upper() == 'CTRL+UA'):
        return 'science'
    return ''


def apply_editorial_sources_237(store: Any) -> dict[str, Any]:
    reports: list[dict[str, Any]] = []
    with store.transaction() as con:
        con.execute('BEGIN IMMEDIATE')
        channels = con.execute(
            'SELECT id,name,channel_mode,editorial_runtime_profile,dedupe_profile '
            'FROM channels WHERE enabled=1 AND channel_mode=\'editorial\''
        ).fetchall()
        for channel in channels:
            role = _canonical_role(channel)
            if not role:
                continue
            cid = int(channel['id'])
            spec = SCIENCE_RSS if role == 'science' else CREATIVE_RSS
            key = MARKER + str(cid)
            hints_key = HINT_MARKER + str(cid)
            hints = [dict(name=name, url=url, role='topic_hint_only',
                          verified_primary_required=True, media_allowed=False)
                     for name,url,roles in TOPIC_HINTS if role in roles]
            # No 'telegram' row is inserted into sources: fan posts may never
            # bypass the actual publisher's facts and first-party media.
            con.execute('INSERT INTO meta(key,value) VALUES(?,?) '
                        'ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                        (hints_key,json.dumps({'version':VERSION,'hints':hints},ensure_ascii=False)))
            if con.execute('SELECT 1 FROM meta WHERE key=?',(key,)).fetchone():
                reports.append({'channel_id':cid,'role':role,'status':'already_applied',
                                'feed_assignments':len(spec),'topic_hints':len(hints)})
                continue
            present = con.execute(
                'SELECT id,name,url,kind,enabled,initialized FROM sources WHERE channel_id=?',
                (cid,),
            ).fetchall()
            by_url = {canonical_feed(str(item['url'])): item for item in present}
            added, reenabled, existing = [], [], []
            for name,url,priority in spec:
                canonical = canonical_feed(url)
                if not canonical:
                    continue
                row = by_url.get(canonical)
                if row is not None:
                    # Explicit new operator instruction re-enables this exact
                    # canonical feed without resetting its history/checkpoint.
                    if not int(row['enabled']) and str(row['kind']) == 'rss':
                        con.execute('UPDATE sources SET enabled=1 WHERE id=? AND channel_id=?',
                                    (int(row['id']),cid))
                        reenabled.append(name)
                    else:
                        existing.append(name)
                    continue
                legacy = json.dumps({'editorial_sources_237':{
                    'introduced_in':VERSION,'role':role,'discovery_only':False,
                    'operator_network_verified':False,'do_not_replay_history':True,
                }},ensure_ascii=False)
                con.execute(
                    'INSERT OR IGNORE INTO sources '
                    '(channel_id,name,url,kind,enabled,initialized,priority,legacy_config_json) '
                    "VALUES (?,?,?,'rss',1,0,?,?)",
                    (cid,name,url,priority,legacy),
                )
                if int(con.execute('SELECT changes()').fetchone()[0]):
                    added.append(name)
            report = {'channel_id':cid,'role':role,'status':'applied',
                      'feed_assignments':len(spec),'added':added,
                      'reenabled':reenabled,'existing':existing,
                      'topic_hints':len(hints),
                      'existing_rows_preserved':True,'backfill':False,
                      'operator_network_verified':False}
            con.execute('INSERT INTO meta(key,value) VALUES(?,?)',
                        (key,json.dumps({'at':now_iso(),**report},ensure_ascii=False)))
            reports.append(report)
        con.commit()
    for report in reports:
        event('ingest','2.3.27 full editorial RSS portfolio registered',**report)
    return {'version':VERSION,'channels':reports,
            'rss_assignments':sum(x['feed_assignments'] for x in reports),
            'hint_definitions':len(TOPIC_HINTS),
            'live_feed_validation_required':True}


def source_portfolio_snapshot_237(store: Any) -> dict[str, Any]:
    """Read-only proof of 31 assignments and six non-publishing TG hints.

    HTTP health is based on actual collector runs, NEVER inferred from a
    successful migration or an editorial model. Do not include all old feeds.
    """
    channels = []
    with store.connect() as con:
        rows = con.execute(
            "SELECT id,name,channel_mode,editorial_runtime_profile,dedupe_profile "
            "FROM channels WHERE enabled=1 AND channel_mode='editorial'"
        ).fetchall()
        for channel in rows:
            role=_canonical_role(channel)
            if not role:
                continue
            cid=int(channel['id'])
            spec=SCIENCE_RSS if role=='science' else CREATIVE_RSS
            current = con.execute('''
                SELECT s.id,s.name,s.url,s.enabled,h.last_outcome,h.last_error,h.last_added
                FROM sources s LEFT JOIN source_health h ON h.source_id=s.id
                WHERE s.channel_id=?''',(cid,)).fetchall()
            byurl={canonical_feed(str(r['url'])):r for r in current}
            items=[]
            for name,url,_ in spec:
                row=byurl.get(canonical_feed(url))
                items.append({'name':name,'feed':url,'registered':bool(row),
                              'enabled':bool(int(row['enabled'])) if row else False,
                              'last_outcome':str(row['last_outcome'] or '') if row else '',
                              'last_error':str(row['last_error'] or '')[:140] if row else '',
                              'last_added':int(row['last_added'] or 0) if row else 0})
            hint_row=con.execute('SELECT value FROM meta WHERE key=?',(HINT_MARKER+str(cid),)).fetchone()
            try:
                hints=json.loads(str(hint_row[0]))['hints'] if hint_row else []
            except (ValueError,KeyError,TypeError):
                hints=[]
            channels.append({'channel_id':cid,'channel_name':str(channel['name']),
                             'role':role,'expected_feeds':len(spec),
                             'registered_feeds':sum(bool(i['registered']) for i in items),
                             'enabled_feeds':sum(bool(i['enabled']) for i in items),
                             'hints_topic_only':len(hints),'feeds':items})
    return {'version':VERSION,'channels':channels,
            'rss_channel_assignments':sum(x['registered_feeds'] for x in channels),
            'tg_hint_sources':len(TOPIC_HINTS),
            'tg_hints_auto_publishing':False,
            'operator_network_verified_by_collector':True}
