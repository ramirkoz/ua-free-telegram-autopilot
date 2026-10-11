from telegram_autopilot.fact_guard import strip_monitoring_nonform_urls


def test_monitoring_removes_article_links_even_when_source_has_details():
    row = {
        "raw_text": "Детальніше на сторінці https://example.com/news/story",
        "source_url": "https://example.com/news/story",
    }
    body = "Опис матеріалу. Детальніше: https://example.com/news/story"
    assert "https://" not in strip_monitoring_nonform_urls(row, body)


def test_monitoring_preserves_only_form_link_proven_in_source():
    row = {
        "raw_text": "Для реєстрації заповніть форму https://example.com/registration"
                    " Детальніше https://example.com/news/story",
    }
    body = ("Зареєструйтеся: https://example.com/registration "
            "Докладніше https://example.com/news/story "
            "https://example.com/fabricated")
    result = strip_monitoring_nonform_urls(row, body)
    assert "https://example.com/registration" in result
    assert "https://example.com/news/story" not in result
    assert "https://example.com/fabricated" not in result
