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


def test_210_real_article_42602_telegram_channel_not_registration():
    from telegram_autopilot.fact_guard import actionable_source_urls
    row = {
        "raw_text": (
            "На окупованих територіях росгвардійці проводять уроки мужності. "
            "Детальніше у телеграм-каналі: https://t.me/five_redakcia"
        ),
        "source_url": "https://t.me/five_redakcia/111211",
        "source_name": "5 РЕДАКЦІЯ",
    }
    assert actionable_source_urls(row["raw_text"], source_name=row["source_name"]) == []
    body = ("На окупованих територіях росгвардійці проводять уроки мужності.\n\n"
            "Деталі/реєстрація: https://t.me/five_redakcia")
    cleaned = strip_monitoring_nonform_urls(row, body)
    assert "five_redakcia" not in cleaned
    assert "Деталі/реєстрація" not in cleaned
    assert "росгвардійці" in cleaned


def test_210_reject_telegram_channel_even_if_source_mentions_registration():
    from telegram_autopilot.fact_guard import actionable_source_urls
    row = {"raw_text": "Реєстрація на подію триває. Читайте новини: https://t.me/five_redakcia"}
    assert actionable_source_urls(row["raw_text"]) == []
    assert "t.me" not in strip_monitoring_nonform_urls(row, "Реєстрація: https://t.me/five_redakcia")


def test_210_explicit_form_link_stays_with_reader():
    from telegram_autopilot.fact_guard import actionable_source_urls
    raw = "Для реєстрації заповніть форму https://forms.gle/AbCdEf123"
    row = {"raw_text": raw}
    assert actionable_source_urls(raw) == ["https://forms.gle/AbCdEf123"]
    assert "https://forms.gle/AbCdEf123" in strip_monitoring_nonform_urls(
        row, "Реєстрація: https://forms.gle/AbCdEf123")


def test_210_telegram_bot_start_link_may_remain_with_explicit_registration():
    from telegram_autopilot.fact_guard import actionable_source_urls
    raw = "Для реєстрації запустіть бота https://t.me/CommunitySignupBot?start=apply2026"
    assert actionable_source_urls(raw) == ["https://t.me/CommunitySignupBot?start=apply2026"]
