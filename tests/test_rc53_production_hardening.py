from __future__ import annotations

from types import SimpleNamespace

from telegram_autopilot.models import Channel
from telegram_autopilot.rc53_hardening import (
    _is_quality_prompt,
    editorial_hard_reject,
    extract_page_published_at,
    infer_date_from_url,
    normalize_url_rc53,
    operator_reaction_breakdown,
    semantic_output_blockers,
)


def _channel(name: str, profile: str = "") -> Channel:
    return Channel(
        id=1,
        name=name,
        telegram_chat_id="@test",
        editorial_profile=profile,
        enabled=True,
        include_source_link=False,
        poll_interval_minutes=5,
        min_publish_interval_minutes=0,
        dedupe_window_hours=72,
        max_age_hours=24,
        max_posts_per_cycle=3,
        created_at="2026-08-30T00:00:00+00:00",
        updated_at="2026-08-30T00:00:00+00:00",
    )


def test_rc53_strips_adweek_itm_campaign_and_common_trackers():
    left = normalize_url_rc53(
        "https://www.adweek.com/foo/?itm_campaign=6&utm_source=x&fbclid=abc&id=42"
    )
    right = normalize_url_rc53(
        "https://www.adweek.com/foo?itm_campaign=4&utm_medium=y&id=42"
    )
    assert left == right == "https://www.adweek.com/foo?id=42"


def test_rc53_query_order_is_canonical():
    assert normalize_url_rc53("https://example.com/a?z=2&a=1") == normalize_url_rc53(
        "https://example.com/a?a=1&z=2"
    )


def test_rc53_extracts_article_published_time():
    html = """
    <html><head>
      <meta property="article:published_time" content="2026-08-29T10:15:00Z">
    </head><body></body></html>
    """
    assert extract_page_published_at(html, "https://example.com/story").startswith(
        "2026-08-29T10:15:00"
    )


def test_rc53_infers_full_date_from_url_only():
    assert infer_date_from_url("https://example.com/2026/08/29/story").startswith("2026-08-29")
    assert infer_date_from_url("https://example.com/2026/08/story") == ""


def test_rc53_operator_reactions_ignore_audience_counts_and_keep_double_choice():
    def item(emoji: str, count: int, chosen=False, chosen_order=None):
        return SimpleNamespace(
            count=count,
            chosen=chosen,
            chosen_order=chosen_order,
            reaction=SimpleNamespace(emoticon=emoji),
        )

    message = SimpleNamespace(
        views=1000,
        forwards=7,
        replies=SimpleNamespace(replies=3),
        reactions=SimpleNamespace(
            results=[
                item("👍", 500, chosen=True, chosen_order=0),
                item("🔥", 120, chosen=True, chosen_order=1),
                item("👎", 30, chosen=False, chosen_order=None),
            ]
        ),
    )
    assert operator_reaction_breakdown(message) == (1000, 7, 3, 1, 0, 1, 0)


def test_rc53_operator_reactions_do_not_learn_from_audience_only():
    message = SimpleNamespace(
        views=20,
        forwards=0,
        replies=None,
        reactions=SimpleNamespace(
            results=[
                SimpleNamespace(
                    count=19,
                    chosen=False,
                    chosen_order=None,
                    reaction=SimpleNamespace(emoticon="👍"),
                )
            ]
        ),
    )
    assert operator_reaction_breakdown(message)[3:6] == (0, 0, 0)


def test_rc53_current_rc51_prompts_are_quality_routed():
    assert _is_quality_prompt(
        "Ты выпускающий редактор Telegram. Подготовь короткий ВНУТРЕННИЙ план"
    )
    assert _is_quality_prompt(
        "Ти пишеш ФІНАЛЬНИЙ пост для Telegram, а не коротку статтю"
    )
    assert not _is_quality_prompt("Classify this article into a category")


def test_rc53_ctrlua_vetoes_known_offtopic_regression():
    ch = _channel("CTRL+UA", "technology, science, AI")
    reason = editorial_hard_reject(ch, {"title": "Tim Curry returns for a new TV special"})
    assert "HARD VETO" in reason


def test_rc53_prodano_vetoes_personnel_regression():
    ch = _channel("ПРОДАНО!", "marketing, advertising, brands")
    reason = editorial_hard_reject(
        ch, {"title": "Agency appoints new Chief Creative Officer"}
    )
    assert "кадрова" in reason


def test_rc53_semantic_qa_blocks_observed_corruption():
    issues = semantic_output_blockers(
        "The team developed new structural epoxies for the composite.",
        "Команда створила нові структурні діоксиди для композиту.",
    )
    assert issues
    assert any("epoxy" in issue for issue in issues)


def test_rc53_semantic_qa_blocks_broken_playoff_form():
    assert semantic_output_blockers(
        "A team reached the playoff.",
        "Система працює після плей-оф ного ривка.",
    )
