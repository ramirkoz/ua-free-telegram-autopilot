"""Regression tests for the v2.3.33 15-Nov operator false positives.

No network, production Data changes, or Telegram actions.
"""
import pytest
from types import SimpleNamespace

from telegram_autopilot.v2.mission_milestone_2333 import mission_milestone_key_2333, mission_milestone_same_event_2333
from telegram_autopilot.v2.event_dedupe_guard import event_fingerprint_same_event, EventFingerprintDedupeEngine
from telegram_autopilot.v2.editorial_owner_2332 import monitoring_source_reason_2332, editorial_source_reason_2332
from telegram_autopilot.v2.editorial import hard_editorial_reject
from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode, ChannelPolicy, EditorialRuntimeProfile
from telegram_autopilot.v2.editorial_human_calibration_236 import MARKER

VERGE = {
    "title": "Watch SpaceX successfully execute the first chopstick catch of Starship",
    "raw_text": "SpaceX captured Starship using the arms of Mechazilla for the first time. After aborting a planned catch of Starship Flight 15's booster, SpaceX captured the Starship vehicle itself at the launch and catch tower.",
    "source_id": 1,
}
SPACE = {
    "title": "What's next for SpaceX's Starship after epic Flight 15 chopsticks catch?",
    "raw_text": "Starship's 15th test flight saw a successful catch. SpaceX sought to return both the Super Heavy booster and Ship upper stage to the tower chopstick arms. The Ship upper stage was caught by the tower after the test flight.",
    "source_id": 2,
}
GUARDIAN = {
    "title": "SpaceX's Starship returns to launch pad from orbit – video",
    "raw_text": "The top part of SpaceX's Starship returned to its Texas launch tower. The Starship 15th test flight envisioned a double catch, but the lower booster exploded over the ocean.",
    "source_id": 3,
}


@pytest.mark.parametrize("a,b", [(VERGE,SPACE),(SPACE,GUARDIAN),(VERGE,GUARDIAN)])
def test_all_three_sources_one_completed_milestone(a,b):
    assert mission_milestone_key_2333(a) == mission_milestone_key_2333(b) != ""
    assert mission_milestone_same_event_2333(a,b)[0]
    assert event_fingerprint_same_event(a,b,compound_events=True)[0]


@pytest.mark.parametrize("title,body", [
    ("SpaceX successfully catches Starship on Flight 16", "The upper stage was caught by the launch tower on Starship Flight 16."),
    ("SpaceX successfully catches Super Heavy booster on Flight 15", "A booster catch was completed at the tower. The upper-stage catch happened earlier."),
    ("SpaceX plans the next Starship catch on Flight 15", "The upper stage is planned to return to its launch tower."),
    ("SpaceX new investigation reveals cause of failure on Flight 15", "New analysis of the upper stage tower catch confirms a separate failure cause."),
    ("NASA completes moon lander flight 15", "The lander returned to base after its test flight."),
])
def test_independent_missions_and_confirmed_updates_are_not_duplicates(title,body):
    assert not mission_milestone_same_event_2333(VERGE, {"title":title,"raw_text":body,"source_id":44})[0]


def test_mere_brand_not_a_milestone():
    assert mission_milestone_key_2333({"title":"SpaceX reports new Raptor engine design","raw_text":"New engine specifications for flight 15."}) == ""


def test_ready_published_ledger_block_before_other_event_memory(monkeypatch):
    current={**GUARDIAN, "id":101757,"channel_id":1,"stage":"READY","decision":"PUBLISH"}
    previous={**VERGE, "id":101251,"channel_id":1,"stage":"PUBLISHED","decision":"PUBLISH"}
    class Store:
        def get_article(self,id): return current if id == 101757 else previous
        def get_channel(self,id): return SimpleNamespace(mode=ChannelMode.EDITORIAL,published_dedupe_window_hours=168)
    dedupe=object.__new__(EventFingerprintDedupeEngine)
    dedupe.store=Store()
    monkeypatch.setattr(dedupe,"_ledger_candidates",lambda *args:[previous])
    result=dedupe._find_duplicate(101757,published_only=True)
    assert result.relation == "DUPLICATE" and result.duplicate_of == 101251


@pytest.mark.parametrize("title,raw",[
    ("17 листопада у Запоріжжі відбудеться поховання сержанта", "17 листопада 2026 року у Запоріжжі відбудеться поховання військовослужбовця."),
    ("Завтра поховають військового", "Завтра поховають військового із громади."),
])
def test_upcoming_funeral_blocked(title,raw):
    region=ChannelConfig(id=3,name="region",telegram_chat_id="-1003",mode=ChannelMode.MONITORING,policy=ChannelPolicy(channel_id=3))
    assert monitoring_source_reason_2332({"title":title,"raw_text":raw}) == "MONITORING_FUTURE_FUNERAL_NOTICE_2333"
    assert hard_editorial_reject(region,{"title":title,"raw_text":raw},"READY candidate") == "MONITORING_FUTURE_FUNERAL_NOTICE_2333"


@pytest.mark.parametrize("title,body",[
    ("Громада повідомила про загибель захисника", "Військовослужбовець загинув. Про дату прощання повідомлять додатково."),
    ("Учора у громаді поховали захисника", "Вчора відбулося прощання та поховання військового, жителі вшанували пам'ять."),
    ("На Запоріжжі тимчасово не працює номер 102", "За технічних причин 102 не працює, дзвоніть 112."),
])
def test_completed_or_important_regional_news_preserved(title,body):
    assert monitoring_source_reason_2332({"title":title,"raw_text":body}) == ""


def test_noncreative_social_survey_rejected_even_with_independent_opinion():
    creative=ChannelConfig(id=2,name="ПРОДАНО!",telegram_chat_id="-1002",mode=ChannelMode.EDITORIAL,
                           editorial_runtime_profile=EditorialRuntimeProfile.COMMERCIAL_EDITORIAL,
                           policy=ChannelPolicy(channel_id=2,selection_rules=MARKER+" дизайн"))
    article={"title":"The right message can shift support for universal basic income across party lines",
             "raw_text":"A social science survey investigated public support for universal basic income across party lines. "*5}
    assert editorial_source_reason_2332("creative",article) == "CREATIVE_PUBLIC_POLICY_OPINION_SURVEY_NOT_CREATIVE_2333"
    assert hard_editorial_reject(creative,article,"old READY text") == "CREATIVE_PUBLIC_POLICY_OPINION_SURVEY_NOT_CREATIVE_2333"
    assert editorial_source_reason_2332("creative",{"title":"Artist makes a visual design campaign on universal basic income",
      "raw_text":"An original poster design uses a new visual identity for social policy."}) == ""
