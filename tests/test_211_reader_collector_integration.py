"""2.1.1 source fallback integrates only after weak native extraction."""
import json
from telegram_autopilot import collector
from telegram_autopilot.models import CollectedArticle
from telegram_autopilot.source_readers import ReaderResult


def test_opt_in_weak_native_source_recovers_original_url(monkeypatch):
    monkeypatch.setattr(collector, "_source_fetch", lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("blocked")))
    seen = []
    def fake(url, *, enabled, timeout):
        seen.append((url, enabled, timeout))
        return ReaderResult(text="Article body. " * 60, original_url=url,
                            reader="jina", reader_url="https://r.jina.ai/https://example.com/story")
    monkeypatch.setattr(collector, "read_with_jina", fake)
    article = CollectedArticle("x","Editorial title","https://example.com/story","",None,[])
    result = collector._enrich_article(article, reader_fallback_enabled=True)
    assert seen[0][0] == "https://example.com/story"
    assert result.url == "https://example.com/story"
    assert result.raw_text.startswith("Article body.")
    assert json.loads(result.article_layout_json)["source_reader"]["mode"] == "jina_fallback"
    assert result.media_urls == []


def test_reader_disabled_does_not_call_service(monkeypatch):
    monkeypatch.setattr(collector, "_source_fetch", lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("blocked")))
    def forbidden(*args, **kwargs):
        raise AssertionError("reader unexpectedly contacted")
    monkeypatch.setattr(collector, "read_with_jina", forbidden)
    result = collector._enrich_article(CollectedArticle("y", "News", "https://example.com/abc", "", None, []))
    assert not result.raw_text


def test_healthy_native_body_is_not_sent_to_reader(monkeypatch):
    class Resp:
        body = b"<html><main><h1>Good news</h1><p>Evidence content.</p></main></html>"
    class Extracted:
        text = "Strong source text. " * 30
        media_urls = ["https://example.com/original.jpg"]
        layout_json = "{}"
        title = "A factual headline"
    monkeypatch.setattr(collector, "_source_fetch", lambda *args, **kwargs: Resp())
    monkeypatch.setattr(collector, "extract_article_content", lambda *args, **kwargs: Extracted())
    monkeypatch.setattr(collector, "read_with_jina", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not call reader")))
    article = CollectedArticle("z", "News", "https://example.com/abc", "", None, [])
    result = collector._enrich_article(article, reader_fallback_enabled=True)
    assert result.media_urls == ["https://example.com/original.jpg"]
    assert "source_reader" not in result.article_layout_json


def test_failed_reader_keeps_original_rss_summary(monkeypatch):
    monkeypatch.setattr(collector, "_source_fetch", lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("blocked")))
    monkeypatch.setattr(collector, "read_with_jina", lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("reader down")))
    article = CollectedArticle("k","News","https://example.com/story","Existing RSS summary",None,["https://example.com/hero.jpg"])
    result = collector._enrich_article(article, reader_fallback_enabled=True)
    assert result.raw_text == "Existing RSS summary"
    assert result.media_urls == ["https://example.com/hero.jpg"]
