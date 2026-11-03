"""2.3.5: editorially relevant commercial feed expansion, without wiping Data.

Explicit Product Owner request of 02 Nov 2026: add sources with consumer-facing
creative/brand/design stories. Do not alter custom entries, duplicate domains,
source age policy, Telegram delivery journals, or other editorial channels.

Public RSS index checks do NOT imply those feeds work in operator's network.
No network requests are made at startup. Reader/QA policies remain unchanged.
"""
from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlsplit

from .loghub import event
from .storage import now_iso

MARKER_PREFIX = 'commercial_sources_235_once_channel_'
VERSION = '2.3.5'

# Exact operator-supplied source identities. Both were disabled legacy PAGE
# sources; restore original rows so that article/source foreign keys survive.
# Previously custom-edited URLs or renamed sources are left unchanged.
RESTORE_ORIGINAL: tuple[tuple[str, str, str, int], ...] = (
    ('The Dieline', 'https://thedieline.com/', 'https://thedieline.com/feed/', 11),
    ('Trend Hunter', 'https://www.trendhunter.com/', 'http://feeds.feedburner.com/TrendHunter/Top10', 17),
)

# Distinct publishers only. Noncommercial art/architecture/product catalog posts
# must still independently pass the broad-audience and factual selectors.
ADD_VERIFIED: tuple[tuple[str, str, str, int], ...] = (
    ('designboom — Design', 'https://www.designboom.com/design/feed/', 'rss', 20),
    ('Dezeen — Design', 'https://www.dezeen.com/design/feed/', 'rss', 21),
    ('Packaging of the World', 'https://packagingoftheworld.com/feed', 'rss', 23),
    ('Colossal', 'https://www.thisiscolossal.com/feed/', 'rss', 30),
)

# Only our original commercial profile, not user-created channels.
# Known URLs are based on operator baseline in the 02 Nov database.
KNOWN_PRESET_ANCHORS = {
    ('Yanko Design', 'https://www.yankodesign.com/feed/'),
    ('Creative Bloq', 'https://www.creativebloq.com/feeds.xml'),
    ('Muse by Clio', 'https://musebyclios.com/feed/'),
    ('Campaign Brief', 'https://campaignbrief.com/feed/'),
}


def _host(url: str) -> str:
    try:
        host = (urlsplit(url).hostname or '').casefold()
        return host[4:] if host.startswith('www.') else host
    except ValueError:
        return ''


def _extra(value: Any) -> dict:
    try:
        result = json.loads(str(value or '{}'))
        return result if isinstance(result, dict) else {}
    except (ValueError, TypeError):
        return {}


def apply_commercial_sources_235(store: Any) -> dict[str, Any]:
    results = []
    with store.transaction() as con:
        con.execute('BEGIN IMMEDIATE')
        rows = con.execute(
            "SELECT id,name FROM channels WHERE editorial_runtime_profile='commercial_editorial'"
        ).fetchall()
        for channel in rows:
            cid = int(channel['id'])
            key = MARKER_PREFIX + str(cid)
            if con.execute('SELECT 1 FROM meta WHERE key=?', (key,)).fetchone():
                results.append({'channel_id': cid, 'outcome': 'already_applied'})
                continue
            sources = con.execute(
                'SELECT id,name,url,kind,enabled,priority,legacy_config_json '
                'FROM sources WHERE channel_id=?', (cid,)
            ).fetchall()
            if not sources:
                results.append({'channel_id': cid, 'outcome': 'no_sources_yet'})
                continue
            if sum((str(r['name']), str(r['url'])) in KNOWN_PRESET_ANCHORS for r in sources) < 3:
                results.append({'channel_id': cid, 'outcome': 'custom_sources_unchanged'})
                continue

            added: list[str] = []
            restored: list[str] = []
            skipped: list[dict] = []
            by_name = {str(r['name']): r for r in sources}
            existing_hosts = {_host(str(r['url'])) for r in sources}
            for name, old_url, rss_url, priority in RESTORE_ORIGINAL:
                r = by_name.get(name)
                if r is None:
                    skipped.append({'name': name, 'reason': 'operator_removed_or_missing'})
                    continue
                if str(r['url']) != old_url or str(r['kind']) != 'page' or int(r['enabled']) != 0:
                    skipped.append({'name': name, 'reason': 'operator_alternative_or_already_enabled'})
                    continue
                host = _host(rss_url)
                if con.execute(
                    'SELECT id FROM sources WHERE channel_id=? AND url=? AND id<>?',
                    (cid, rss_url, int(r['id'])),
                ).fetchone():
                    skipped.append({'name': name, 'reason': 'same_feed_already_exists'})
                    continue
                # For other publishers, existing domain presence is enough to
                # avoid auto-reviving against an operator's alternative source.
                if any(_host(str(other['url'])) == host and int(other['id']) != int(r['id'])
                       for other in sources):
                    skipped.append({'name': name, 'reason': 'feed_host_in_use'})
                    continue
                settings = _extra(r['legacy_config_json'])
                settings['commercial_sources_235'] = {
                    'old_url': old_url, 'new_url': rss_url, 'added_in': VERSION,
                    'public_feed_index_verified': True,
                    'operator_network_verified': False,
                    'selection_guards_unchanged': True,
                }
                con.execute(
                    "UPDATE sources SET url=?,kind='rss',enabled=1,initialized=0,"
                    "priority=?,last_checked_at='',last_error='',legacy_config_json=? "
                    "WHERE id=? AND channel_id=? AND name=? AND url=? AND enabled=0",
                    (rss_url, priority, json.dumps(settings, ensure_ascii=False),
                     int(r['id']), cid, name, old_url),
                )
                if con.execute('SELECT changes()').fetchone()[0]:
                    # Health is historical telemetry. Clear stale PAGE errors,
                    # keep all source IDs and article references unchanged.
                    con.execute(
                        "UPDATE source_health SET consecutive_failures=0,cooldown_until='',"
                        "last_outcome='RSS_RESTORED_235',last_error='',"
                        "zero_result_streak=0,slow_streak=0,last_duration_ms=0,"
                        "last_items=0,last_added=0,updated_at=? WHERE source_id=?",
                        (now_iso(), int(r['id'])),
                    )
                    restored.append(name)
                    existing_hosts.add(host)

            for name, url, kind, priority in ADD_VERIFIED:
                host = _host(url)
                if not host or host in existing_hosts:
                    skipped.append({'name': name, 'reason': 'existing_publisher_host'})
                    continue
                info = json.dumps({'commercial_sources_235': {
                    'added_in': VERSION, 'public_feed_index_verified': True,
                    'operator_network_verified': False,
                    'selection_guards_unchanged': True,
                }}, ensure_ascii=False)
                con.execute(
                    'INSERT OR IGNORE INTO sources '
                    '(channel_id,name,url,kind,enabled,initialized,priority,legacy_config_json) '
                    'VALUES (?,?,?,?,1,0,?,?)',
                    (cid, name, url, kind, priority, info),
                )
                if con.execute('SELECT changes()').fetchone()[0]:
                    added.append(name)
                    existing_hosts.add(host)
            report = {
                'channel_id': cid, 'outcome': 'applied', 'added': added,
                'restored': restored, 'skipped': skipped,
                'active_sources': int(con.execute(
                    'SELECT count(*) FROM sources WHERE channel_id=? AND enabled=1', (cid,)
                ).fetchone()[0]),
            }
            con.execute('INSERT INTO meta(key,value) VALUES(?,?)',
                        (key, json.dumps({'at': now_iso(), **report}, ensure_ascii=False)))
            results.append(report)
        con.commit()
    for report in results:
        event('ingest', '2.3.5 commercial editorial source portfolio', **report)
    return {'version': VERSION, 'channels': results, 'operator_network_verified': False}


__all__ = ['apply_commercial_sources_235', 'ADD_VERIFIED', 'RESTORE_ORIGINAL']
