"""2.2.56: broad-audience channel identity and catalog-vs-story safety."""
import inspect
import json
from types import SimpleNamespace

from telegram_autopilot.v2.ai_gateway import AIResult
from telegram_autopilot.v2.commercial_reader_256 import (
    COMMERCIAL_READER_RULE_256, commercial_reader_veto_256,
    normalized_reader_signal_256,
)
from telegram_autopilot.v2.domain import (
    ChannelConfig, ChannelMode, EditorialRuntimeProfile,
)
from telegram_autopilot.v2.editorial import EditorialEngine
from telegram_autopilot.v2 import runtime_contracts


def article(title="Tiny Forest Sauna", raw_text="A tiny forest sauna needs no major excavation."):
    return {"id": 256, "title": title, "raw_text": raw_text}


def metrics(**extra):
    base = {
        "decision":"publish", "fit_score":96, "reason":"cool-looking",
        "commercial_mechanism":90, "consumer_behavior":90, "creative_execution":90,
        "measurable_result":90, "strategic_transferability":90, "why_now":90,
        "general_interest":90, "retellability":90, "culture_signal":90,
        "surprise_or_conflict":90, "consumer_relevance":90,
        "story_class":"routine_object", "shareable_to_friend":False,
        "product_only":True, "share_hook_quote":"",
    }
    base.update(extra)
    return base


def test_high_scores_do_not_rescue_catalog_only_story():
    assert commercial_reader_veto_256(article(), metrics()).startswith("SOLD_CATALOG_ONLY_256")


def test_source_verified_surprise_can_rescue_product_story():
    a = article("Giant shoe for dogs", "A dog-sized shoe doubles as a pet bed in a surprising collaboration.")
    m = metrics(story_class="routine_object", product_only=True,
                shareable_to_friend=True, share_hook_quote="dog-sized shoe doubles as a pet bed")
    assert commercial_reader_veto_256(a, m) == ""


def test_ai_invented_source_quote_cannot_rescue_catalog():
    m = metrics(shareable_to_friend=True,
                share_hook_quote="millions of fans turned it into a viral meme")
    assert commercial_reader_veto_256(article(), m).startswith("SOLD_CATALOG_ONLY_256")


def test_noncatalog_has_no_source_name_or_brand_blacklist():
    a = article("Yanko Design: robot goose", "The robot goose has an unusual home-assistance function.")
    for typ in ("viral_culture", "brand_stunt", "unexpected_use", "human_behavior",
                "surprising_research", "remarkable_object", "other"):
        m = metrics(story_class=typ, product_only=False,
                    shareable_to_friend=True, share_hook_quote="unusual home-assistance function")
        assert commercial_reader_veto_256(a, m) == ""


def test_unknown_metrics_from_legacy_are_backwards_compatible():
    assert commercial_reader_veto_256(article(), {"general_interest": 80}) == ""


def test_catalog_still_rejected_without_quote_even_if_friend_boolean_true():
    m = metrics(shareable_to_friend=True, share_hook_quote="")
    assert commercial_reader_veto_256(article(), m).startswith("SOLD_CATALOG_ONLY_256")


def test_short_vague_quote_is_not_proof():
    m = metrics(shareable_to_friend=True, share_hook_quote="sauna")
    assert commercial_reader_veto_256(article(), m).startswith("SOLD_CATALOG_ONLY_256")


def test_raw_source_quote_normalizes_whitespace():
    m = metrics(shareable_to_friend=True,
                share_hook_quote="no    major  excavation")
    assert commercial_reader_veto_256(article(), m) == ""


def test_positive_examples_are_orientations_not_whitelist():
    assert "плюшевий манул IKEA" in COMMERCIAL_READER_RULE_256
    assert "Adidas × Pokémon" in COMMERCIAL_READER_RULE_256
    assert "резюме на торті" in COMMERCIAL_READER_RULE_256
    assert "НЕ whitelist" in COMMERCIAL_READER_RULE_256
    assert "крихітний будинок" in COMMERCIAL_READER_RULE_256


def test_reader_fields_normalization():
    s = normalized_reader_signal_256(metrics(story_class="illegal", product_only=False))
    assert s["story_class"] == "other"
    assert s["signal_present"]


class FakeLearning:
    def topic_assessment(self, channel_id, article):
        return SimpleNamespace(hard_suppress=False, fit_adjustment=0)
    def topic_memory_block(self, channel_id, article):
        return ""


class FakeGateway:
    def __init__(self, data):
        self.data = data
        self.calls = []
    def run(self, prompt, **kwargs):
        self.calls.append((prompt, kwargs))
        raw = json.dumps(self.data, ensure_ascii=False)
        kwargs["validator"](raw)
        return AIResult(raw, "gemini", "gemini-3.5-flash", "Gemini", ())


def _channel(commercial=True):
    return ChannelConfig(
        id=382, name="Random Channel Not PRODANO", telegram_chat_id="@test",
        mode=ChannelMode.EDITORIAL,
        editorial_runtime_profile=(
            EditorialRuntimeProfile.COMMERCIAL_EDITORIAL if commercial
            else EditorialRuntimeProfile.STANDARD
        ),
    )


def _combined_result(data, a, commercial=True):
    gateway=FakeGateway(data)
    original=EditorialEngine._select_editorial
    try:
        runtime_contracts._install_ai_efficiency_contract()
        eng=EditorialEngine(None, gateway)
        eng.learning=FakeLearning()
        outcome=eng._select_editorial(_channel(commercial), a)
    finally:
        EditorialEngine._select_editorial=original
    return outcome, gateway.calls


def test_live_rc102_path_rejects_boring_catalog_without_extra_ai():
    outcome, calls=_combined_result(metrics(), article())
    assert str(outcome.decision) == "REJECT"
    assert "SOLD_CATALOG_ONLY_256" in outcome.reason
    assert len(calls) == 1
    assert calls[0][1]["purpose"] == "editorial_selector"
    assert "плюшевий манул IKEA" in calls[0][0]
    assert "Чи захоче" in calls[0][0] or "чи захоче" in calls[0][0]


def test_live_rc102_path_accepts_astonishing_story():
    a=article("IKEA manul plush", "IKEA launched a plush manul for fans of the wild cat.")
    good=metrics(story_class="viral_culture", product_only=False,
                 shareable_to_friend=True, share_hook_quote="plush manul for fans")
    outcome,calls=_combined_result(good,a)
    assert str(outcome.decision) == "PUBLISH"
    assert len(calls)==1


def test_noncommercial_channel_not_affected():
    data=metrics()
    data.update(novelty=90, consequence_or_insight=90, mechanism=90,
                reader_payoff=90, concrete_stakes=90, why_now=90,
                curiosity_only=False)
    out,calls=_combined_result(data,article(),commercial=False)
    assert "SOLD_CATALOG_ONLY_256" not in out.reason
    assert "плюшевий манул IKEA" not in calls[0][0]


def test_fallback_editorial_selector_has_commercial_reader_rule():
    src=inspect.getsource(EditorialEngine._select_editorial)
    assert "commercial_reader_veto_256" in src
    assert "COMMERCIAL_READER_RULE_256" in src
