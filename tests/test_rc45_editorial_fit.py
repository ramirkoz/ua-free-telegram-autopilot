from telegram_autopilot import rc45_policy
from telegram_autopilot.rc45_editorial_fit import install_rc45_editorial_fit, needs_semantic_profile_review


def test_rc45_evergreen_and_conference_titles_require_semantic_profile_review():
    assert needs_semantic_profile_review("WAN vs LAN explained: what is the difference?")
    assert needs_semantic_profile_review("The top ten best optical illusions")
    assert needs_semantic_profile_review("IEEE student conference for budding authors")
    assert needs_semantic_profile_review("Що таке генеративний ШІ: пояснюємо")
    assert not needs_semantic_profile_review("Google launches a new Gemini transcription model")


def test_rc45_profile_review_disables_only_cheap_lexical_shortcut():
    install_rc45_editorial_fit()
    categories = [{"name": "AI", "weight": 100}]
    evergreen = {"title": "AI explained: what is an AI agent?", "raw_text": "AI agent AI agent"}
    breaking = {"title": "AI company launches agent platform", "raw_text": "AI company launches agent platform"}
    assert rc45_policy.lexical_category(evergreen, categories) == ""
    assert rc45_policy.lexical_category(breaking, categories) == "AI"
