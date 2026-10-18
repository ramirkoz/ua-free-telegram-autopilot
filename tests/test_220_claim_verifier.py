from types import SimpleNamespace

from telegram_autopilot.v2.claim_verifier import verify_qualified_claims
from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode, ChannelPolicy
from telegram_autopilot.v2.editorial import prepublish_quality_issues


def test_uncertain_injury_claim_cannot_become_certain():
    source = "Попередньо повідомляють про пошкодження трьох житлових будинків."
    final = "Пошкодження трьох житлових будинків підтверджено."
    violations = verify_qualified_claims(source, final, source_id="community/100")
    assert violations
    assert violations[0].code == "MONITORING_UNCERTAINTY_ESCALATION"
    assert violations[0].source_quote in source


def test_preserved_uncertainty_is_not_blocked():
    source = "Попередньо повідомляють про пошкодження трьох житлових будинків."
    final = "Попередньо повідомляють про пошкодження трьох житлових будинків."
    assert not verify_qualified_claims(source, final, source_id="community/100")


def test_unrelated_confirmed_fact_not_affected():
    source = (
        "Попередньо повідомляють про пошкодження трьох житлових будинків. "
        "У громаді провели засідання ради."
    )
    final = "У громаді провели засідання ради."
    assert not verify_qualified_claims(source, final, source_id="community/100")


def test_prepublication_gate_blocks_laundered_certainty():
    channel = ChannelConfig(
        id=3, name="ГРОМАДИ", telegram_chat_id="@test",
        mode=ChannelMode.MONITORING,
        policy=ChannelPolicy(monitoring_source_policy="connected_original"),
    )
    raw = "Попередньо повідомляють про пошкодження трьох житлових будинків."
    article = SimpleNamespace(
        id=101, title="Повідомлення", raw_text=raw,
        source_name="Місцева редакція", source_url="https://example.org/news",
        media_json="[]", article_layout_json="{}",
    )
    issues = prepublish_quality_issues(
        channel, article,
        "Пошкодження трьох житлових будинків підтверджено.",
    )
    assert "MONITORING_UNCERTAINTY_ESCALATION" in issues
