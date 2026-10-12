"""2.1.1 reader opt-in and binding regression tests."""
import pytest
from telegram_autopilot import source_readers as readers


@pytest.mark.parametrize("url", [
    "http://localhost:8080/admin", "http://127.0.0.1/private",
    "http://10.0.0.1", "http://192.168.1.2",
    "http://169.254.169.254/latest", "http://[::1]/",
    "https://foo.internal/secret", "https://t.me/example",
    "file:///etc/passwd", "https://user:pass@example.com/article",
    "https://example.com:8080/article",
])
def test_invalid_targets_never_reach_external_reader(url):
    assert not readers.eligible_article_url(url)
    with pytest.raises(ValueError):
        readers.jina_reader_url(url)


def test_opt_in_defaults_off(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("network must stay unused by default")
    monkeypatch.setattr(readers, "fetch_url", forbidden)
    assert readers.read_with_jina("https://example.com/news/article") is None


def test_source_identity_retained_and_bounds_respected(monkeypatch):
    called = []
    class Response:
        body = (b"Evidence text from a source. " * 35)
    def fake(url, **kwargs):
        called.append((url, kwargs))
        return Response()
    monkeypatch.setattr(readers, "fetch_url", fake)
    url = "https://example.com/news/real-article"
    result = readers.read_with_jina(url, enabled=True)
    assert result is not None
    assert result.original_url == url
    assert result.reader == "jina"
    assert result.text.startswith("Evidence")
    assert called[0][0].startswith("https://r.jina.ai/https://example.com/")
    assert called[0][1]["max_bytes"] == 512 * 1024
    assert called[0][1]["timeout"] <= 15


def test_short_reader_result_is_rejected(monkeypatch):
    class Response:
        body = b"no"
    monkeypatch.setattr(readers, "fetch_url", lambda *args, **kwargs: Response())
    assert readers.read_with_jina("https://example.com/a", enabled=True) is None
