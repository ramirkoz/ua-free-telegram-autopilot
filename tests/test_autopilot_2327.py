"""2.3.27 safe portfolio, cost attribution and editorial economy regressions."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from telegram_autopilot.v2.storage import V2Store, now_iso
from telegram_autopilot.v2.editorial_sources_237 import (
    SCIENCE_RSS, CREATIVE_RSS, TOPIC_HINTS, HINT_MARKER,
    apply_editorial_sources_237, canonical_feed,
)
from telegram_autopilot.v2.ai_economics_237 import ai_article_scope, economics_snapshot
from telegram_autopilot.v2.reader_first import (
    writer_reader_rules, final_reader_rules, requires_final_reader_copyedit,
)


class Test2327(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store=V2Store(Path(self.tmp.name)/'test.sqlite3')
        with self.store.connect() as con:
            for cid,name,profile,dedupe in [
                (1,'CTRL+UA','standard','scientific_news'),
                (2,'ПРОДАНО!','commercial_editorial','standard'),
                (3,'ГРОМАДИ','standard','standard'),
            ]:
                con.execute('''INSERT INTO channels(id,name,channel_mode,editorial_runtime_profile,dedupe_profile,created_at,updated_at)
                              VALUES (?,?,?, ?,?,?,?)''',
                            (cid,name,'editorial' if cid!=3 else 'monitoring',profile,dedupe,now_iso(),now_iso()))

    def test_portfolio_installs_every_rss_at_once(self):
        self.assertEqual(len(SCIENCE_RSS),15)
        self.assertEqual(len(CREATIVE_RSS),16)
        self.assertEqual(len({canonical_feed(item[1]) for item in SCIENCE_RSS+CREATIVE_RSS}),29)
        self.assertEqual(len(TOPIC_HINTS),6)
        result=apply_editorial_sources_237(self.store)
        self.assertEqual(result['rss_assignments'],31)
        with self.store.connect() as con:
            for cid,size in ((1,15),(2,16),(3,0)):
                self.assertEqual(con.execute('SELECT COUNT(*) FROM sources WHERE channel_id=?',(cid,)).fetchone()[0],size)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM sources WHERE kind='telegram'").fetchone()[0],0)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM sources WHERE initialized=0').fetchone()[0],31)
            for cid, expected in ((1,4),(2,4)):
                rows=con.execute('SELECT value FROM meta WHERE key=?',(HINT_MARKER+str(cid),)).fetchone()
                self.assertEqual(len(json.loads(rows[0])['hints']),expected)
            self.assertIsNone(con.execute('SELECT value FROM meta WHERE key=?',(HINT_MARKER+'3',)).fetchone())

    def test_restart_idempotent_and_custom_operator_rows_unchanged(self):
        with self.store.connect() as con:
            con.execute("INSERT INTO sources(id,channel_id,name,url,kind,enabled,initialized,priority) VALUES (901,2,'Creative Review',?,'rss',0,1,5)",
                        ('https://www.creativereview.co.uk/feed/',))
            con.execute("INSERT INTO sources(id,channel_id,name,url,kind,enabled,initialized,priority) VALUES (902,2,'Custom Source','https://example.net/feed','rss',0,1,7)")
            con.execute("INSERT INTO sources(id,channel_id,name,url,kind,enabled,initialized,priority) VALUES (903,2,'Fast Company','https://www.fastcompany.com/co-design/rss','rss',0,1,10)")
        first=apply_editorial_sources_237(self.store)
        second=apply_editorial_sources_237(self.store)
        self.assertEqual(second['channels'][0]['status'],'already_applied')
        with self.store.connect() as con:
            # Original primary key + history + initialisation retained.
            old=con.execute('SELECT enabled,initialized,priority FROM sources WHERE id=901').fetchone()
            self.assertEqual(tuple(old),(1,1,5))
            custom=con.execute('SELECT enabled,initialized,priority FROM sources WHERE id=902').fetchone()
            self.assertEqual(tuple(custom),(0,1,7))
            original=con.execute('SELECT enabled FROM sources WHERE id=903').fetchone()
            self.assertEqual(int(original[0]),0)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM sources WHERE channel_id=2 AND enabled=1').fetchone()[0],16)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM sources WHERE channel_id=3').fetchone()[0],0)

    def test_editorial_prompt_not_mandatory_for_monitoring(self):
        self.assertIn('ГАЧОК',writer_reader_rules(monitoring=False,commercial=True)) if False else None
        self.assertIn('Фактичний «гачок»',writer_reader_rules(monitoring=False,commercial=True))
        self.assertIn('350–600',final_reader_rules(monitoring=False,commercial=False,science=True))
        self.assertNotIn('350–600',writer_reader_rules(monitoring=True,commercial=False))
        self.assertFalse(requires_final_reader_copyedit(monitoring=False,legacy_quality_risk=False))
        self.assertTrue(requires_final_reader_copyedit(monitoring=False,legacy_quality_risk=True))

    def test_cost_attribution_scoped_and_old_rows_still_supported(self):
        with ai_article_scope(1,111):
            self.store.record_ai_usage(provider='openrouter',model='test',purpose='writer',actual_openrouter_usd=.01)
        self.store.record_ai_usage(provider='openrouter',model='test',purpose='health_probe',actual_openrouter_usd=.002)
        with self.store.connect() as con:
            data=con.execute('SELECT channel_id,article_id,actual_openrouter_usd FROM ai_usage_events ORDER BY id').fetchall()
            self.assertEqual((int(data[0][0]),int(data[0][1])),(1,111))
            self.assertEqual((int(data[1][0]),int(data[1][1])),(0,0))
        actual=economics_snapshot(self.store)
        self.assertAlmostEqual(actual['actual_openrouter_usd'],.012,places=6)
        self.assertEqual(actual['committed_24h'],0)
        self.assertIsNone(actual['usd_per_committed_post'])
        self.assertAlmostEqual(actual['charged_unattributed_legacy_or_non_article'],.002,places=6)
        self.assertIn('SPEND_WITH_ZERO_DELIVERIES',actual['alerts'])

    def test_delivery_window_and_cost_per_committed(self):
        now=datetime.now(timezone.utc).astimezone()
        with self.store.connect() as con:
            con.execute("INSERT INTO sources(id,channel_id,name,url,kind) VALUES (10,1,'src','https://example.org/feed','rss')")
            con.execute('''INSERT INTO articles(id,channel_id,source_id,external_id,source_url,canonical_source_url,discovered_at)
                           VALUES (111,1,10,'111','https://example.org/a','https://example.org/a',?)''',(now_iso(),))
            con.execute('''INSERT INTO publication_delivery_journal(article_id,channel_id,state,committed_at)
                           VALUES (111,1,'COMMITTED',?)''',(now.isoformat(),))
        with ai_article_scope(1,111):
            self.store.record_ai_usage(provider='openrouter',model='gpt',purpose='writer',actual_openrouter_usd=.008)
        result=economics_snapshot(self.store)
        self.assertEqual(result['committed_24h'],1)
        self.assertEqual(result['committed_by_channel']['1'],1)
        self.assertEqual(result['usd_per_committed_post'],.008)
        self.assertEqual(result['charged_by_channel_attributed']['1'],.008)

if __name__=='__main__':unittest.main()

class Test2327Media(unittest.TestCase):
    def test_before_writer_missing_required_media_defers(self):
        from unittest.mock import patch,MagicMock
        from telegram_autopilot.v2.editorial_media_preflight_237 import (
            ensure_media_for_editorial_writer,MediaPreflightPending)
        from telegram_autopilot.v2.domain import ChannelMode
        channel=MagicMock()
        channel.mode=ChannelMode.EDITORIAL
        channel.policy.normalized_media_policy.return_value='required'
        channel.id=2
        article={'id':99,'source_url':'https://example.org/story',
                 'canonical_source_url':'https://example.org/story'}
        empty=MagicMock(count=0)
        with patch('telegram_autopilot.v2.media_pipeline.build_publication_media_bundle',return_value=empty):
            with patch('telegram_autopilot.v2.publisher.Publisher') as Publisher:
                Publisher.return_value._recover_missing_source_media.return_value=(article,empty,'no_source_media')
                with self.assertRaises(MediaPreflightPending):
                    ensure_media_for_editorial_writer(MagicMock(),channel,article)

    def test_valid_existing_media_skips_network_recovery(self):
        from unittest.mock import patch,MagicMock
        from telegram_autopilot.v2.editorial_media_preflight_237 import ensure_media_for_editorial_writer
        from telegram_autopilot.v2.domain import ChannelMode
        channel=MagicMock()
        channel.mode=ChannelMode.EDITORIAL
        channel.policy.normalized_media_policy.return_value='required'
        article={'id':9}
        with patch('telegram_autopilot.v2.media_pipeline.build_publication_media_bundle',return_value=MagicMock(count=1)):
            with patch('telegram_autopilot.v2.publisher.Publisher') as publisher:
                self.assertIs(ensure_media_for_editorial_writer(MagicMock(),channel,article),article)
                publisher.assert_not_called()
