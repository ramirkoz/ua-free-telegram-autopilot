from telegram_autopilot.v2.publisher import _publication_text_cleanup


def test_semenivska_raw_markdown_and_orphan_video_label():
    posted = "**Усиновлення в Україні: що потрібно знати**\n\nВідомості про документи та курс.\n\nПереглянути відео:\n"
    cleaned = _publication_text_cleanup(posted)
    assert cleaned.startswith("Усиновлення в Україні: що потрібно знати")
    assert "**" not in cleaned
    assert "Переглянути відео:" not in cleaned
    assert "Відомості про документи та курс." in cleaned


def test_real_video_link_must_never_be_erased_by_markup_cleanup():
    posted = "**Усиновлення в Україні**\n\nПереглянути відео: https://youtu.be/exampleABC"
    cleaned = _publication_text_cleanup(posted)
    assert "https://youtu.be/exampleABC" in cleaned
    assert "**" not in cleaned


def test_ordinary_asterisk_not_removed():
    assert _publication_text_cleanup("Формула 2*3 і документи") == "Формула 2*3 і документи"
