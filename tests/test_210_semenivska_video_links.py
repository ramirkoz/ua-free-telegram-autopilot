"""2.1.0 regression: Semenivska adoption video action and format safety."""
from telegram_autopilot.fact_guard import (
    actionable_source_urls, strip_monitoring_nonform_urls, clean_orphan_video_cues,
)
from telegram_autopilot.v2.editorial import restore_practical_literals

VIDEO = "https://www.youtube.com/watch?v=AdoptionGuide123"
SOURCE = (
    "Усиновлення в Україні: що потрібно знати?\n"
    "Основні етапи процедури.\n"
    "Переглянути відео на YouTube: " + VIDEO + "\n"
    "Єдина державна платформа dity.gov.ua"
)
ARTICLE = {
    "raw_text": SOURCE, "source_name": "Семенівська сільська військова адміністрація",
    "source_url": "https://t.me/semenivskatg/6869",
    "canonical_source_url": "https://t.me/semenivskatg/6869",
    "media_json": "[]", "article_layout_json": "{}",
}


def test_real_video_action_is_preserved():
    assert actionable_source_urls(SOURCE) == [VIDEO]
    output = strip_monitoring_nonform_urls(
        ARTICLE, "Усиновлення: що потрібно знати?\n\nПереглянути відео: " + VIDEO
    )
    assert VIDEO in output


def test_real_video_link_is_restored_when_source_url_present():
    output = restore_practical_literals(
        ARTICLE, "Усиновлення: практичні етапи процедури.", hard_max_chars=750
    )
    assert VIDEO in output
    assert "Переглянути відео" in output


def test_missing_link_does_not_create_false_video_cta():
    source_without_url = dict(ARTICLE, raw_text="Переглянути відео на YouTube")
    output = strip_monitoring_nonform_urls(source_without_url, "Новина.\n\nПереглянути відео:")
    assert "Переглянути відео" not in output
    assert output == "Новина."


def test_plain_attribution_not_action():
    source = "Про інформацію повідомляє канал https://t.me/five_redakcia"
    assert actionable_source_urls(source) == []
    assert strip_monitoring_nonform_urls(dict(ARTICLE, raw_text=source), "Деталі: https://t.me/five_redakcia") == ""


def test_no_trailing_orphan_and_no_video_invention():
    source = "Процедура усиновлення. Переглянути відео:"
    assert actionable_source_urls(source) == []
    assert clean_orphan_video_cues("Порядок усиновлення.\n\nПереглянути відео:") == "Порядок усиновлення."
