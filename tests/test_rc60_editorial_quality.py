from telegram_autopilot.rc60_editorial_quality import (
    _cross_source_title_match,
    latin_jargon_issues,
)


def test_cross_source_dedupe_chatgpt_dsa_event():
    current = "EU designates ChatGPT a very large online search engine under DSA"
    old = {"title": "ChatGPT now faces stricter EU oversight as a very large search engine"}
    match = _cross_source_title_match(current, old)
    assert match is not None
    assert match[0] >= 0.90


def test_cross_source_dedupe_chipotle_100_creators_event():
    current = "Fernando Machado just let 100 creators loose in 50 Chipotle kitchens"
    old = {"title": "Chipotle deploys 100 creators for latest ads spotlighting fresh food"}
    match = _cross_source_title_match(current, old)
    assert match is not None
    assert match[0] >= 0.89


def test_cross_source_dedupe_does_not_merge_unrelated_same_brand_story():
    current = "Chipotle deploys 100 creators for latest ads spotlighting fresh food"
    old = {"title": "Chipotle raises menu prices after avocado costs increase"}
    assert _cross_source_title_match(current, old) is None


def test_language_mix_flags_translatable_professional_jargon():
    text = (
        "Кампанія працює як social-first запуск. Бренд показав run rate і creator payouts, "
        "а потім додав hot takes у ролик."
    )
    issues = latin_jargon_issues(text)
    assert "social-first" in issues
    assert "run rate" in issues
    assert "creator payouts" in issues
    assert "hot takes" in issues


def test_language_mix_allows_real_names_models_and_acronyms():
    text = "ChatGPT працює з API, а Unreal Engine 5 використовується разом із PX4 та Python."
    assert latin_jargon_issues(text) == ()
