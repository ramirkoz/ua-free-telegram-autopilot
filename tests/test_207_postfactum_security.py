from types import SimpleNamespace
from telegram_autopilot.v2.editorial import _postfactum_security_policy, deterministic_monitoring_exclusion
from telegram_autopilot.v2.domain import ChannelMode


def channel(rules="Тільки постфактум, підсумки за добу. Без тривог, вибухів та диму."):
    return SimpleNamespace(
        mode=ChannelMode.MONITORING,
        policy=SimpleNamespace(selection_rules="Публікувати підтверджені підсумки за добу", rejection_rules=rules),
    )


def article(body):
    return {"title": "", "raw_text": body}


def test_live_blast_is_rejected_before_ai():
    assert "POSTFACTUM_ONLY" in deterministic_monitoring_exclusion(channel(), article("Олександрівський, фпв. Вибух був."))


def test_live_smoke_is_rejected():
    assert "POSTFACTUM_ONLY" in _postfactum_security_policy(channel(), article("У громаді видно дим."))


def test_postfactum_recap_is_allowed():
    assert _postfactum_security_policy(
        channel(), article("За минулу добу було атаковано громаду. Пошкоджено два будинки.")
    ) == ""


def test_arbitrary_news_not_affected():
    assert _postfactum_security_policy(channel(), article("У громаді відкрили бібліотеку.")) == ""


def test_other_monitoring_policy_not_affected():
    assert _postfactum_security_policy(
        channel("Протокольні привітання заборонено."),
        article("Олександрівський, фпв. Вибух був."),
    ) == ""
