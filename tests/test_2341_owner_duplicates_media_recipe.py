"""LIVE 2026-11-19 owner regressions; source-only, no operator Data or Telegram."""
from copy import deepcopy

from telegram_autopilot.v2.dedupe import _same_event
from telegram_autopilot.v2.editorial_live_2339 import source_same_event_without_update
from telegram_autopilot.v2.editorial_live_2341 import (
    same_zaporizhzhia_daily_attack_bulletin_2341,
    creative_ordinary_cooking_recipe_reason_2341,
)
from telegram_autopilot.media_pipeline import (
    PreparedMedia, _creativeboom_source_media_proof_2341, _semantic_media_match,
)

FIRST = {
    "source_id": 203,
    "source_url": "https://t.me/info_zp/174410",
    "source_published_at": "2026-11-19T07:11:58+02:00",
    "title": "554 удари по 50 населених пунктах Запорізької області протягом доби",
    "raw_text": ("554 удари по 50 населених пунктах Запорізької області протягом доби. "
                 "Одна людина загинула, ще шестеро поранені. "
                 "16 авіаційних ударів, 435 різних БпЛА, 3 обстріли з РСЗВ "
                 "і 100 артилерійських ударів."),
}
SECOND = {
    "source_id": 204,
    "source_url": "https://t.me/onenews_zp/154704",
    "source_published_at": "2026-11-19T09:38:07+02:00",
    "title": ("https://1news.zp.ua/odna-lyudyna-zagynula-ta-shhe-shestero-poraneni-"
              "vorog-zavdav-554-udary-po-zaporizkij-oblasti/ "
              "Одна людина загинула, ще шестеро поранені: ворог завдав "
              "554 удари по Запорізькій області"),
    "raw_text": ("Впродовж 18 листопада російська армія завдала 554 удари "
                 "по 50 населеним пунктам Запорізької області. "
                 "Одна людина загинула, ще шестеро поранені. "
                 "3 удари РСЗВ, 16 авіаударів, 100 артударів, 435 БпЛА."),
}


def test_live_duplicate_5294_5298_source_facts_win_over_url_and_date():
    assert same_zaporizhzhia_daily_attack_bulletin_2341(SECOND, FIRST)
    assert source_same_event_without_update(SECOND, FIRST)
    assert _same_event(SECOND, FIRST)[0]


def test_changed_attack_count_is_new_information():
    changed = deepcopy(SECOND)
    changed["title"] = changed["title"].replace("554 удари", "556 ударів")
    changed["raw_text"] = changed["raw_text"].replace("554 удари", "556 ударів")
    assert not same_zaporizhzhia_daily_attack_bulletin_2341(changed, FIRST)


def test_changed_injury_count_must_not_be_suppressed():
    changed = deepcopy(SECOND)
    changed["title"] = changed["title"].replace("шестеро поранені", "семеро поранені")
    changed["raw_text"] = changed["raw_text"].replace("шестеро поранені", "семеро поранені")
    assert not same_zaporizhzhia_daily_attack_bulletin_2341(changed, FIRST)


def test_new_local_incident_not_merged_with_daily_report():
    changed = deepcopy(SECOND)
    changed["raw_text"] = "Новий удар по Запоріжжю: зруйновано будинок."
    assert not same_zaporizhzhia_daily_attack_bulletin_2341(changed, FIRST)


def test_explicitly_different_reporting_dates_preserved():
    changed = deepcopy(SECOND)
    changed["raw_text"] = changed["raw_text"].replace("18 листопада", "17 листопада")
    old = deepcopy(FIRST)
    old["raw_text"] += " За підсумками 18 листопада."
    assert not same_zaporizhzhia_daily_attack_bulletin_2341(changed, old)


def test_next_calendar_day_same_counts_not_suppressed():
    changed = deepcopy(SECOND)
    changed["source_published_at"] = "2026-11-20T09:38:07+02:00"
    assert not same_zaporizhzhia_daily_attack_bulletin_2341(changed, FIRST)


def test_ordinary_thanksgiving_leftover_recipe_is_rejected():
    article = {
        "title": "Ultimate Thanksgiving Leftovers Hoagie Sandwich Recipe",
        "raw_text": "Ingredients for the spread. Step 1: Mix the leftovers. Bake for 10 minutes.",
    }
    assert creative_ordinary_cooking_recipe_reason_2341(article)


def test_real_food_product_or_marketing_story_still_eligible():
    a = {"title": "Innovative robot chef recipe campaign",
         "raw_text": "New robotic chef cooks ramen using novel sensors. Step 1 demonstrates the design."}
    assert not creative_ordinary_cooking_recipe_reason_2341(a)
    b = {"title": "New bakery packaging design changes the shopping experience",
         "raw_text": "Packaging design and food technology."}
    assert not creative_ordinary_cooking_recipe_reason_2341(b)


def test_creativeboom_unrelated_video_thumbnail_even_when_schema_verified():
    wrong = PreparedMedia(
        index=10, kind="image", url="https://www.creativeboom.com/static/other-videos/thumbnail-boat.jpg",
        alt="Making a funny paper boat", caption="Watch this",
        schema_verified=True, page_declared=True, gallery=True,
    )
    source_url = "https://www.creativeboom.com/insight/its-official-creatives-are-using-ai-daily-but-theyre-not-making-extra-money/"
    title = "It's official: creatives are using AI daily, but most aren't making extra money from it"
    body = "Envato surveyed 1,033 creatives from 103 countries; 58% use AI daily"
    assert _semantic_media_match(wrong, title=title, article_text=body)  # prior false-positive
    assert not _creativeboom_source_media_proof_2341(
        wrong, source_url=source_url, title=title, article_text=body)


def test_creativeboom_article_infographic_survives():
    good = PreparedMedia(
        index=3, kind="image", url="https://www.creativeboom.com/insight/report-ai-creatives-chart.jpg",
        alt="58% of creatives use AI daily in the Envato report", caption="Envato research: AI at work",
        schema_verified=True, page_declared=True, gallery=True,
    )
    title = "It's official: creatives are using AI daily, but most aren't making extra money from it"
    body = "Envato surveyed creatives from 103 countries; 58% use AI daily"
    assert _creativeboom_source_media_proof_2341(
        good, source_url="https://www.creativeboom.com/insight/report/",
        title=title, article_text=body)


def test_unrelated_publishers_keep_existing_media_policy():
    item = PreparedMedia(index=4, kind="image", url="https://site.com/image.jpg", alt="foo")
    assert _creativeboom_source_media_proof_2341(
        item, source_url="https://www.yankodesign.com/article/",
        title="Other", article_text="None")
