"""2.3.20 actual production-path regression for editorial correction and sources.

No Telegram sends, remote APIs, legacy replay, or operator Data mutation.
"""
import json
from types import SimpleNamespace

from telegram_autopilot.v2.domain import (
    ChannelMode, ChannelPolicy, EditorialRuntimeProfile, DedupeProfile, Decision,
)
from telegram_autopilot.v2.editorial_human_calibration_236 import MARKER
from telegram_autopilot.v2.editorial_feedback_2320 import calibrated_feedback_2320
from telegram_autopilot.v2.editorial_second_opinion_2320 import (
    eligible_second_opinion_2320, verified_second_opinion_2320,
)
from telegram_autopilot.v2.editorial import EditorialEngine
from telegram_autopilot.v2.commercial_sources_2320 import (
    apply_commercial_sources_2320, SOURCES,
)
from telegram_autopilot.v2.storage import V2Store


def _article(title="E Ink solar picture frame with an unusual function"):
    return {"id": 123400, "title": title,
        "raw_text": ("Designers created an E Ink photo frame driven entirely by "
                     "solar energy, showing curated art without a power outlet. "
                     "The prototype stores energy for use inside ordinary rooms. "
                     "Its creators described how the system works and showed "
                     "an early working prototype to visitors.")}


def test_157_actual_human_labels_scope_and_policy_are_preserved():
    sci = calibrated_feedback_2320("science")
    creative = calibrated_feedback_2320("creative")
    assert "69 зі 100" in sci and "31 відхилив" in sci
    assert "36 із 57" in creative and "21 відхилив" in creative
    assert "22 обрані" in creative
    assert "E Ink" in creative and "GTA VI" in creative and "водоростей" in creative
    assert "Artemis II" in sci and "сенсорні" in sci
    assert calibrated_feedback_2320("monitoring") == ""
    assert "факти" in sci and "Telegram" in creative


def test_second_opinion_is_content_scoped_not_article_id_whitelist():
    assert eligible_second_opinion_2320(_article(), "creative")
    for title in (
        "GTA VI advertising creative campaign with optical illusion",
        "A ring with OLED screen and joystick for new interactions",
        "Art made from algae in an unusual visual installation",
        "A mobile home with new interior spatial design",
    ):
        assert eligible_second_opinion_2320(_article(title), "creative")
    assert not eligible_second_opinion_2320(_article("50 percent discount coupon"), "creative")
    assert not eligible_second_opinion_2320(_article(), "creative", "duplicate")
    assert not eligible_second_opinion_2320(_article(), "creative", "insufficient_facts")
    assert not eligible_second_opinion_2320(_article(), "monitoring")
    assert not eligible_second_opinion_2320(
        {"title": "Brand design campaign", "raw_text": "A short teaser."}, "creative"
    )


def test_second_opinion_demands_exact_source_quote():
    art = _article()
    quote = "solar energy, showing curated art without a power outlet"
    assert verified_second_opinion_2320(
        {"decision": "publish", "source_quote": quote}, art)
    assert not verified_second_opinion_2320(
        {"decision": "publish", "source_quote": "invented claim with fictional sales"}, art)
    assert not verified_second_opinion_2320(
        {"decision": "reject", "source_quote": quote}, art)


class _Learning:
    def topic_assessment(self, cid, article):
        return SimpleNamespace(hard_suppress=False, fit_adjustment=0)
    def topic_memory_block(self, cid, article):
        return ""


def _channel():
    return SimpleNamespace(
        id=2, mode=ChannelMode.EDITORIAL,
        editorial_runtime_profile=EditorialRuntimeProfile.COMMERCIAL_EDITORIAL,
        dedupe_profile=DedupeProfile.STANDARD,
        dedupe_scientific_names=False, dedupe_compound_events=False,
        policy=ChannelPolicy(selection_rules=MARKER+" creative",
                             rejection_rules="no routine PR",
                             purpose="Creative novel stories",
                             audience="General audience"),
    )


class _Gateway:
    def __init__(self, second):
        self.prompts=[]
        self.second=second
    def run(self, prompt, *, validator=None, **kwargs):
        self.prompts.append(prompt)
        if len(self.prompts)==1:
            payload = json.dumps({"decision": "reject", "fit_score": 20,
                                  "reject_code": "weak_audience_hook",
                                  "reason": "ordinary design"})
        else:
            payload=json.dumps(self.second)
        if validator:
            validator(payload)
        return SimpleNamespace(text=payload, provider="test", model="mock")


def _engine(second):
    obj=object.__new__(EditorialEngine)
    obj.store=None
    obj.learning=_Learning()
    obj.gateway=_Gateway(second)
    obj._coverage_reviews_234={}
    return obj


def test_production_selector_rescues_verified_human_false_negative():
    art=_article()
    quote="solar energy, showing curated art without a power outlet"
    engine=_engine({"decision":"publish", "source_quote":quote, "reason":"Novel energy design"})
    outcome=engine._select_editorial(_channel(), art)
    assert outcome.decision == Decision.PUBLISH
    assert "SECOND_OPINION_2320" in outcome.reason
    assert len(engine.gateway.prompts)==2
    assert "36 із 57" in engine.gateway.prompts[0]
    assert "solar energy" in engine.gateway.prompts[1]


def test_production_selector_fails_closed_on_unverifiable_quote():
    art=_article()
    engine=_engine({"decision":"publish", "source_quote":"fabricated success that source never states",
                    "reason":"too optimistic"})
    out=engine._select_editorial(_channel(),art)
    assert out.decision==Decision.REJECT
    assert len(engine.gateway.prompts)==2


def test_source_additions_are_one_time_scoped_and_not_operator_overrides(tmp_path):
    store=V2Store(tmp_path/"news.sqlite3")
    with store.transaction() as con:
        con.execute("INSERT INTO channels(id,name,channel_mode,editorial_runtime_profile,"
                    "created_at,updated_at) VALUES (2,'ПРОДАНО!','editorial',"
                    "'commercial_editorial','2026','2026')")
        for i,(name,url) in enumerate((
            ("Yanko Design","https://www.yankodesign.com/feed/"),
            ("Creative Bloq","https://www.creativebloq.com/feeds.xml"),
            ("Muse by Clio","https://musebyclios.com/feed/"),
        ),start=111):
            con.execute("INSERT INTO sources(id,channel_id,name,url,kind,enabled,initialized,priority) "
                        "VALUES (?,2,?,?,'rss',1,1,25)",(i,name,url))
        con.commit()
    output=apply_commercial_sources_2320(store)
    assert len(output["channels"][0]["added"])==len(SOURCES)
    assert apply_commercial_sources_2320(store)["channels"][0]["status"]=="already_applied"
    with store.connect() as con:
        assert con.execute("SELECT count(*) FROM sources WHERE channel_id=2").fetchone()[0]==6
        assert con.execute("SELECT count(*) FROM sources WHERE initialized=0").fetchone()[0]==3
