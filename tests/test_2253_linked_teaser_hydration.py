"""2.2.53: exact post-owned external detail recovery, defensive negative controls."""
import inspect
import json

import pytest

from telegram_autopilot.models import CollectedArticle
from telegram_autopilot.network import HttpResponse, NetworkError
from telegram_autopilot.v2.bounded_ingest import BoundedStrictIngestService
from telegram_autopilot.v2.editorial_reader_contract_252 import source_completeness_issue
from telegram_autopilot.v2.linked_teaser_hydration_253 import (
    hydrate_linked_teaser, teaser_page_target,
)


def item(title, body, link="https://t.me/news_channel/42"):
    return CollectedArticle(
        external_id="news_channel/42", title=title, url=link,
        raw_text=body, published_at="2026-10-29T16:05:00+02:00",
        media_urls=["image|https://t.me/file/test.jpg"],
        article_layout_json=json.dumps({"telegram": {"source_boundary_provenance": "exact_telegram_widget"}}),
    )


def page(title, body):
    return (
        "<html><head><title>" + title + "</title></head><body>"
        "<article><h1>" + title + "</h1><p>" + body + "</p></article>"
        "</body></html>"
    ).encode("utf-8")


def fake_response(url, html, *, final_url=None, status=200):
    return HttpResponse(status=status, headers={"content-type": "text/html"},
                        body=html, final_url=final_url or url)


def test_renamed_streets_recovered_from_exact_author_link():
    url = "https://zabor.zp.ua/News/new-street-names"
    source = item(
        "У Запоріжжі перейменували три вулиці: які нові назви отримали",
        "У Запоріжжі перейменували три вулиці. Старі назви МВО-7, "
        "Лейтенанта Шмідта та Військкоматська. Детальніше: " + url,
    )
    assert source_completeness_issue(source)
    captured = []
    def fetcher(got, **kwargs):
        captured.append((got, kwargs))
        html = page(
            "У Запоріжжі перейменували три вулиці: нові назви",
            "Міська рада ухвалила рішення про перейменування. "
            "Вулиця МВО-7 стала вулицею Ґрунтовою. "
            "Лейтенанта Шмідта стала вулицею Дар’ї Міхєєвої. "
            "Військкоматська стала вулицею Злагоди. "
            "Рішення ухвалили депутати міської ради під час чергового засідання. "
            "Відтепер у документах використовують відповідні нові назви вулиць.",
        )
        return fake_response(got, html)
    old_media = list(source.media_urls)
    old_url, old_id, old_time = source.url, source.external_id, source.published_at
    result, status = hydrate_linked_teaser(source, fetcher=fetcher)
    assert status == "hydrated"
    assert result is source
    assert not source_completeness_issue(result)
    assert "Ґрунтовою" in result.raw_text and "Злагоди" in result.raw_text
    assert result.url == old_url and result.external_id == old_id
    assert result.published_at == old_time and result.media_urls == old_media
    layout = json.loads(result.article_layout_json)
    assert layout["telegram"]["source_boundary_provenance"] == "exact_telegram_widget"
    assert layout["explicit_linked_article_253"]["imported_media"] is False
    assert layout["explicit_linked_article_253"]["linked_page_url"] == url
    assert len(captured) == 1 and captured[0][0] == url
    assert captured[0][1]["timeout"] <= 8
    assert captured[0][1]["max_bytes"] <= 800000
    assert captured[0][1]["max_redirects"] <= 1


def test_water_addresses_recovered_from_linked_story():
    url = "https://zabor.zp.ua/News/water-stops"
    source = item(
        "У Запоріжжі відключили воду за десятками адрес: повний перелік адрес",
        "Відключили воду через аварію. Повний перелік адрес опубліковано. "
        "Детальніше: " + url,
    )
    assert source_completeness_issue(source)
    body = (
        "У Запоріжжі тривають аварійні роботи на водопровідних мережах. "
        "Вода тимчасово відсутня на вулиці Сонячній, 15 та вулиці Миру, 2. "
        "Ремонтники працюють над відновленням водопостачання. "
        "Деталі про точний час завершення робіт будуть оприлюднені окремо. "
        "Адреси вказані на офіційній сторінці комунального підприємства."
    )
    html = page("У Запоріжжі відключили воду за десятками адрес", body)
    result, status = hydrate_linked_teaser(source, fetcher=lambda u, **kw: fake_response(u, html))
    assert status == "hydrated"
    assert not source_completeness_issue(result)
    assert "Сонячній" in result.raw_text


@pytest.mark.parametrize("link", [
    "http://zabor.zp.ua/news/test",
    "https://127.0.0.1/news",
    "https://192.168.1.1/news",
    "https://localhost.local/news",
    "https://foo.internal/news",
    "https://t.me/another_channel/44",
    "https://test.invalid/news",
    "https://user:pass@news.zp.ua/story",
    "https://news.zp.ua:8080/news",
    "https://news.zp.ua/story#fragment",
])
def test_prohibited_targets_not_fetched(link):
    source = item(
        "У Запоріжжі перейменували три вулиці: які нові назви",
        "Перейменували вулиці. Детальніше: " + link,
    )
    assert teaser_page_target(source) == ""
    def never(url, **kwargs):
        raise AssertionError("untrusted URL was fetched")
    untouched, status = hydrate_linked_teaser(source, fetcher=never)
    assert status == "not_eligible" and untouched is source


def test_exactly_one_link_only_not_a_web_search():
    source = item(
        "У Запоріжжі перейменували три вулиці: які нові назви",
        "Детальніше: https://news.zp.ua/story та Детальніше: https://news.zp.ua/other",
    )
    assert teaser_page_target(source) == ""


def test_good_direct_incident_post_never_fetched():
    source = item(
        "У Запоріжжі FPV-дрон атакував маршрутку",
        "Відомо про одного пораненого. Медики надають допомогу. "
        "Детальніше: https://news.zp.ua/incident",
    )
    assert teaser_page_target(source) == ""
    assert hydrate_linked_teaser(source, fetcher=lambda url, **kw: 1)[1] == "not_eligible"


def test_cross_host_redirect_stays_original():
    source = item(
        "У Запоріжжі перейменували три вулиці: які нові назви",
        "Перейменували вулиці. Детальніше: https://news.zp.ua/renames",
    )
    before = source.raw_text
    html = page("У Запоріжжі перейменували три вулиці", "Вулиця А стала вулицею Б. " * 20)
    _, status = hydrate_linked_teaser(source, fetcher=lambda u, **kw: fake_response(
        u, html, final_url="https://elsewhere.org/news"
    ))
    assert status == "redirect_or_http_mismatch"
    assert source.raw_text == before


def test_unrelated_story_cannot_become_telegram_fact():
    source = item(
        "У Запоріжжі перейменували три вулиці: які нові назви",
        "Перейменували вулиці. Детальніше: https://news.zp.ua/renames",
    )
    before = source.raw_text
    html = page(
        "Погодні умови на півдні України цього тижня",
        "Погодні умови залишатимуться мінливими. " * 12,
    )
    _, status = hydrate_linked_teaser(source, fetcher=lambda u, **kw: fake_response(u, html))
    assert status == "article_identity_unverified"
    assert source.raw_text == before


def test_page_missing_promised_mapping_remains_blocked():
    source = item(
        "У Запоріжжі перейменували три вулиці: які нові назви",
        "Перейменували вулиці. Детальніше: https://news.zp.ua/renames",
    )
    html = page(
        "У Запоріжжі перейменували три вулиці",
        "Міська рада обговорила питання зміни назв деяких міських вулиць. " * 8,
    )
    _, status = hydrate_linked_teaser(source, fetcher=lambda u, **kw: fake_response(u, html))
    assert status == "promised_facts_still_missing"
    assert source_completeness_issue(source)


def test_403_or_timeout_does_not_mutate_existing_item():
    source = item(
        "У Запоріжжі перейменували три вулиці: які нові назви",
        "Перейменували вулиці. Детальніше: https://news.zp.ua/renames",
    )
    original = source.raw_text
    def fail(url, **kwargs):
        raise NetworkError("HTTP 403")
    _, status = hydrate_linked_teaser(source, fetcher=fail)
    assert status == "fetch_or_extract_unavailable"
    assert source.raw_text == original


def test_bounded_ingest_wired_fresh_unseen_and_two_channel_tokens():
    body = inspect.getsource(BoundedStrictIngestService.collect_channel)
    assert "linked_teaser_tokens = [2]" in body
    assert "source.kind == \"telegram\"" in body
    assert "teaser_page_target(item)" in body
    assert "source_freshness_rejection(" in body
    assert "self._existing_reason(" in body
    assert "linked_teaser_tokens[0] -= 1" in body
    assert "hydrate_linked_teaser(item)" in body
