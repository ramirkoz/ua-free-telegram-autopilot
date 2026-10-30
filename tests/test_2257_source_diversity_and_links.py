"""2.2.57: source diversity without quotas and real page-campaign link recovery."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import sqlite3
from types import SimpleNamespace

import pytest

from telegram_autopilot.collector import _LinkParser, collect_source
from telegram_autopilot.models import Source
from telegram_autopilot.v2.commercial_diversity_257 import (
    commercial_published_share_7d, source_concentration_penalty_257,
)
from telegram_autopilot.v2.commercial_yield_237 import prioritize_commercial_sources


def _src(sid, priority=20):
    return SimpleNamespace(id=sid, priority=priority, name=f"feed {sid}", kind="rss")


def test_diverse_sources_get_first_chance_without_losing_dominate_source():
    src = [_src(199, 18), _src(129, 15), _src(97, 14), _src(200, 22)]
    health = [{"source_id": i, "last_added": 0, "last_duration_ms": 600,
               "last_outcome": "KNOWN_ONLY"} for i in (199,129,97,200)]
    yielded = [{"source_id":199, "collected":17, "published":6, "short_source_rejected":0},
               {"source_id":129, "collected":14, "published":1,"short_source_rejected":6},
               {"source_id":97, "collected":2, "published":0,"short_source_rejected":0},
               {"source_id":200, "collected":9, "published":1,"short_source_rejected":0}]
    old=prioritize_commercial_sources(src,health,yielded)
    assert old[0].id == 199  # previously best-published always collected first
    new=prioritize_commercial_sources(
        src,health,yielded,
        published_share_7d={199:.78,129:.11,200:.11},
        published_total_7d=53, published_sources_7d=3,
    )
    assert new[0].id != 199
    assert len(new)==len(src)
    assert {x.id for x in new}=={x.id for x in src}
    assert [x.priority for x in src]==[18,15,14,22]  # in-memory config untouched


@pytest.mark.parametrize("posts,sources", [(0,0),(6,2),(11,3),(25,1)])
def test_low_evidence_or_one_real_source_never_penalized(posts,sources):
    assert source_concentration_penalty_257(199,{199:.8},total_posts=posts,source_count=sources)==0


def test_source_penalty_caps_without_bans():
    assert source_concentration_penalty_257(199,{199:.25},total_posts=40,source_count=3)==0
    assert 0<source_concentration_penalty_257(199,{199:.75},total_posts=40,source_count=3)<=25


class ReadOnlyStore:
    def __init__(self):
        self.con=sqlite3.connect(":memory:")
        self.con.row_factory=sqlite3.Row
        self.con.executescript("""CREATE TABLE articles (
            id INTEGER PRIMARY KEY,channel_id INTEGER,source_id INTEGER,
            published_at TEXT NOT NULL DEFAULT '', decision TEXT NOT NULL DEFAULT ''
        );""")
        recent=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        old=(datetime.now(timezone.utc)-timedelta(days=10)).astimezone().isoformat(timespec="seconds")
        rows=[(i,2,199,recent,"PUBLISH") for i in range(1,9)]
        rows += [(9,2,129,recent,"PUBLISH"),(10,2,200,recent,"PUBLISH")]
        rows += [(11,2,199,"","PUBLISH"),(12,2,199,old,"PUBLISH")]
        rows += [(13,1,199,recent,"PUBLISH")]
        self.con.executemany("INSERT INTO articles VALUES(?,?,?,?,?)",rows)
        self.con.commit()
    @contextmanager
    def connect(self):
        yield self.con


def test_read_only_published_at_not_candidates_or_other_channels():
    store=ReadOnlyStore()
    initial=store.con.total_changes
    signal=commercial_published_share_7d(store,2)
    assert signal["total_posts"]==10
    assert signal["counts"]=={199:8,129:1,200:1}
    assert signal["shares"][199]==.8
    assert store.con.total_changes==initial
    assert signal["operator_source_state_unchanged"] is True


def test_link_parser_handles_void_images_and_nested_headings():
    html="""<html><body>
    <article><a href="/2026/10/mcdonalds-halloween-face-paints/">
      <img src="cover.jpg"><span>McDonald's turns sauces into</span>
      <strong>Halloween face paints</strong><br>today
    </a></article>
    <article><a href="/2026/10/lego-fans/">
      <picture><source srcset="x.webp"><img src="x.jpg"></picture>
      <h3>LEGO builds a giant wave from thousands of flowers</h3>
    </a></article></body></html>"""
    parser=_LinkParser("https://www.famouscampaigns.com/")
    parser.feed(html)
    assert len(parser.links)==2
    assert parser.links[0][0]=="https://www.famouscampaigns.com/2026/10/mcdonalds-halloween-face-paints/"
    assert "Halloween" in parser.links[0][1]
    assert "LEGO" in parser.links[1][1]


def test_page_collector_recovers_campaign_links_with_images(monkeypatch):
    from telegram_autopilot import collector
    html="""<html><body><div>
      <a href="/2026/10/burger-king-marathon-cups/"><img src="x.jpg">
      <h2>Burger King puts marathon runners on ice in giant cups</h2></a>
      <a href="/2026/10/mcdonalds-face-paint/"><img src="y.jpg">
      <span>McDonald's turns sauces into Halloween face paints</span></a>
    </div></body></html>""".encode()
    fetched=[]
    def fetch(url,**kwargs):
        return SimpleNamespace(body=html,final_url=url)
    def enrich(item,**kwargs):
        fetched.append(item.url)
        item.raw_text="Original article with clearly described campaign and real event. "*8
        return item
    monkeypatch.setattr(collector,"_source_fetch",fetch)
    monkeypatch.setattr(collector,"_enrich_article",enrich)
    source=Source(id=126,channel_id=2,kind="page",name="Famous Campaigns",
                  url="https://www.famouscampaigns.com/",enabled=True,
                  initialized=True,last_checked_at=None,last_error=None)
    found=collect_source(source,page_prefer_feed=False,page_fetch_limit=4)
    assert len(found)==2
    assert len(fetched)==2
    assert all("famouscampaigns.com/2026/10/" in x for x in fetched)


def test_source_quote_editorial_gate_and_other_channels_unchanged():
    from telegram_autopilot.v2.commercial_reader_256 import commercial_reader_veto_256
    assert commercial_reader_veto_256(
        {"title":"new compact house","raw_text":"A new compact house with a beautiful wooden facade."},
        {"decision":"publish","story_class":"routine_object","product_only":True,
         "shareable_to_friend":False,"share_hook_quote":""}
    ).startswith("SOLD_CATALOG_ONLY_256")
