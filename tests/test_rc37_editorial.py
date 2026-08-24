from __future__ import annotations

from telegram_autopilot.rc37_policy import _adaptive_source_backoff_seconds, newsworthiness_reject_reason
from telegram_autopilot.rc37_style import interest_style_issues, style_examples_for_article


def article(title: str, raw: str = "This is a sufficiently long English technology article. " * 20):
    return {"title": title, "raw_text": raw, "source_priority": 100}


def test_rc37_rejects_non_news_formats_even_from_high_priority_source() -> None:
    titles = (
        "The best Kindle accessories in 2026",
        "Wi-Fi 6 vs Wi-Fi 7: what's the difference and which is better?",
        "Apple CarPlay: 5 reasons Siri may not work and fixes",
        "Poetry for engineers: Safe Distance",
        "Software Should Work and talking about it needn't be boring",
    )
    for title in titles:
        assert newsworthiness_reject_reason(article(title)).startswith("NEWSWORTHINESS_SKIP")


def test_rc37_keeps_real_news() -> None:
    titles = (
        "CISA orders urgent patching of actively exploited Zimbra flaw",
        "Kyoto University demonstrates a SiC transistor that runs at 600C",
        "Astronomers find the earliest galaxy swallowed by the Milky Way",
        "Microsoft confirms August update breaks PDF export in WPF apps",
        "Teacher sues after AI deepfake incident",
    )
    for title in titles:
        assert newsworthiness_reject_reason(article(title)) == ""


def test_rc37_rejects_unrelated_multi_topic_editorial_mashup() -> None:
    title = "AI vendors turn to custom hardware as Microsoft winds back the clock on Windows"
    assert newsworthiness_reject_reason(article(title)).startswith("NEWSWORTHINESS_SKIP")


def test_rc37_style_examples_are_topic_near_and_bounded() -> None:
    rows = style_examples_for_article(article("Microsoft Windows PDF printing bug"), limit=2)
    assert 1 <= len(rows) <= 2
    assert any("Windows" in row for row in rows)


def test_rc37_interest_gate_flags_ai_scaffolding() -> None:
    boring = (
        "Microsoft підтвердила проблему в оновленні Windows.\n\n"
        "Водночас система продовжує працювати в інших сценаріях.\n\n"
        "Для широкої аудиторії це важливо як приклад змін.\n\n"
        "Таким чином, користувачам варто стежити за оновленнями."
    )
    issues = interest_style_issues(boring)
    assert "слабкий канцелярський початок замість новинного гачка" in issues
    assert "шаблонні AI-переходи/мета-пояснення" in issues


def test_rc37_adaptive_backoff_grows_for_chronic_429_and_bad_feed() -> None:
    first = _adaptive_source_backoff_seconds({"last_error": "HTTP 429", "total_errors": 1})
    chronic = _adaptive_source_backoff_seconds({"last_error": "HTTP 429", "total_errors": 20})
    bad_feed = _adaptive_source_backoff_seconds({"last_error": "Unexpected content type: text/html; expected feed", "total_errors": 8})
    assert first >= 30 * 60
    assert chronic > first
    assert bad_feed >= 4 * 3600


def test_rc37_story_reedit_allows_hook_restructure_without_new_facts() -> None:
    from telegram_autopilot.rc37_style import preserves_story_reedit
    original = (
        "Microsoft підтвердила, що серпневе оновлення Windows спричиняє збій друку й PDF. "
        "Проблема стосується WPF-застосунків. Тимчасовий обхід послаблює захист оновлення."
    )
    edited = (
        "Серпневе оновлення Windows принесло збій друку й PDF. "
        "Microsoft підтвердила проблему у WPF-застосунках. Тимчасовий обхід послаблює захист."
    )
    assert preserves_story_reedit(original, edited)
