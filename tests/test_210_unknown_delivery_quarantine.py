"""2.0.10: never retry or repeatedly mutate unknown Telegram sends."""
from telegram_autopilot.v2.publisher import Publisher


class _Store:
    def __init__(self):
        self.fail_calls = 0
        self.backoff_calls = 0
        self.row = {"last_error_code": "DELIVERY_OUTCOME_UNKNOWN"}

    def delivery_journal(self, article_id):
        return {"state": "UNKNOWN", "last_error": "Telegram outcome unknown"}

    def get_article(self, article_id):
        return self.row

    def fail_delivery(self, *args, **kwargs):
        self.fail_calls += 1

    def publication_backoff(self, *args, **kwargs):
        self.backoff_calls += 1


class _Channel:
    id = 3


def test_unknown_delivery_is_stable_and_never_blind_retried():
    store = _Store()
    publisher = object.__new__(Publisher)
    publisher.store = store
    for _ in range(5):
        assert publisher._delivery_preflight(39392, _Channel()) == "DELIVERY_OUTCOME_UNKNOWN"
    assert store.fail_calls == 0
    assert store.backoff_calls == 0


def test_first_unknown_delivery_is_quarantined_once():
    store = _Store()
    store.row = {"last_error_code": ""}
    publisher = object.__new__(Publisher)
    publisher.store = store
    assert publisher._delivery_preflight(39392, _Channel()) == "DELIVERY_OUTCOME_UNKNOWN"
    assert store.fail_calls == 1
    assert store.backoff_calls == 1
