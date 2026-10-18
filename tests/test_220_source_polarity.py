from types import SimpleNamespace

from telegram_autopilot.v2.polarity_verifier import verify_source_polarity
from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode, ChannelPolicy
from telegram_autopilot.v2.editorial import prepublish_quality_issues


def test_missing_electricity_is_not_rewritten_as_available():
    source = "У селі немає електропостачання через пошкодження мережі."
    output = "У селі є електропостачання через пошкодження мережі."
    findings = verify_source_polarity(source, output, source_id="community/200")
    assert len(findings) == 1
    assert findings[0].code == "MONITORING_SOURCE_POLARITY_FLIP"


def test_no_electricity_statement_preserved():
    source = "У селі немає електропостачання через пошкодження мережі."
    assert not verify_source_polarity(source, source, source_id="community/200")


def test_unrelated_source_sentences_are_not_forced_to_match():
    source = "У селі немає електропостачання через пошкодження мережі. У громаді пройшла зустріч з волонтерами."
    output = "У громаді пройшла зустріч з волонтерами."
    assert not verify_source_polarity(source, output, source_id="community/200")


def test_prepublication_gate_wires_source_polarity_check():
    channel = ChannelConfig(
        id=3, name="ГРОМАДИ", telegram_chat_id="@test",
        mode=ChannelMode.MONITORING,
        policy=ChannelPolicy(monitoring_source_policy="connected_original"),
    )
    original = "У селі немає електропостачання через пошкодження мережі."
    article = SimpleNamespace(
        id=200, title="Стан електропостачання", raw_text=original,
        source_name="Місцева громада", source_url="https://example.org/story",
        media_json="[]", article_layout_json="{}",
    )
    issues = prepublish_quality_issues(
        channel, article, "У селі є електропостачання через пошкодження мережі."
    )
    assert "MONITORING_SOURCE_POLARITY_FLIP" in issues
