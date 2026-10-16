from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from telegram_autopilot.v2.commercial_freshness import source_is_stale
from telegram_autopilot.v2.commercial_campaign_guard import campaign_key,prior_published_campaign

def test_freshness_source_date_only():
    assert source_is_stale((datetime.now(timezone.utc)-timedelta(days=3)).isoformat())
    assert not source_is_stale((datetime.now(timezone.utc)-timedelta(hours=3)).isoformat())
    assert not source_is_stale("")

def test_campaign_identity_not_just_brand():
    assert campaign_key("Orange Scamcophony annoying music") == "orange:scamcophony"
    assert campaign_key("Orange introduces 5G") == ""
    assert campaign_key("Vodafone Scamcophony") == ""

def test_duplicate_across_different_newsroom_wordings():
    class Conn:
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def execute(self,*args):return self
        def fetchall(self):
            return [dict(id=47,title="Orange Scamcophony",raw_text="Orange created a cacophony to repel scam calls",final_text="")]
    class Store:
        def connect(self):return Conn()
    article={"title":"Orange кампанія проти шахрайських дзвінків","raw_text":"Скамкофон і музика проти телефонного спаму","final_text":""}
    assert prior_published_campaign(Store(),2,50,article)==47
    assert prior_published_campaign(Store(),1,50,article)==0
