from telegram_autopilot import network


class FakeResponse:
    status = 200
    def getheaders(self):
        return [("Content-Type", "image/jpeg")]
    def read(self, limit):
        return b"test-image"


class FakeConnection:
    targets = []
    def __init__(self, host, ip, port, timeout):
        self.host = host
    def connect(self):
        pass
    def request(self, method, path, body=None, headers=None):
        # http.client enforces this byte-level ASCII contract.
        path.encode("ascii")
        self.targets.append(path)
    def getresponse(self):
        return FakeResponse()
    def close(self):
        pass


def test_2111_unicode_hero_url_and_encoded_query(monkeypatch):
    FakeConnection.targets.clear()
    monkeypatch.setattr(network, "_PinnedHTTPSConnection", FakeConnection)
    url = "https://example.com/новини/hero—фото.jpg?name=тест—image&keep=%2F"
    result = network.fetch_url(url, resolver=lambda host, port: ["8.8.8.8"])
    assert result.status == 200
    target = FakeConnection.targets[-1]
    assert "%D0%BD%D0%BE%D0%B2%D0%B8%D0%BD%D0%B8" in target
    assert "%E2%80%94" in target
    assert "keep=%2F" in target
    assert "%252F" not in target


def test_2111_already_escaped_and_reserved_url_unchanged(monkeypatch):
    FakeConnection.targets.clear()
    monkeypatch.setattr(network, "_PinnedHTTPSConnection", FakeConnection)
    original = "/hero%20image.jpg?size=1200&crop=top%2Fleft"
    network.fetch_url("https://example.com" + original, resolver=lambda host, port: ["8.8.8.8"])
    assert FakeConnection.targets[-1] == original
