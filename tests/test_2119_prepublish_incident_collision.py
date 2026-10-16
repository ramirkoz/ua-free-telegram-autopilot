from datetime import datetime, timedelta
from types import SimpleNamespace
from telegram_autopilot.v2.incident_guard import recent_community_incident_duplicate


class DummyContext:
    def __init__(self, rows):
        self.rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, *_):
        return self

    def fetchall(self):
        return self.rows


class Store:
    def __init__(self, rows):
        self.rows = rows

    def connect(self):
        return DummyContext(self.rows)


class Row(dict):
    pass


def test_real_world_58853_vs_58682():
    at = (datetime.now().astimezone() - timedelta(minutes=5)).isoformat()
    row = Row(
        article_id=58682, title="За оновленою інформацією поранена 73-річна жінка",
        raw_text="Внаслідок ворожого удару пошкоджено будинок та поранена жінка.",
        final_text="У Запорізькій області внаслідок ворожого удару поранена 73-річна жінка.",
        published_at=at,
    )
    current = {
        "title": "Відомо про щонайменше 2 поранених внаслідок удару по Запоріжжю",
        "raw_text": "Відомо про щонайменше 2 поранених внаслідок удару по Запоріжжю",
        "final_text": "У Запоріжжі внаслідок удару поранено щонайменше двох людей.",
    }
    assert recent_community_incident_duplicate(Store([row]), 3, 58853, current) == 58682


def test_unrelated_community_coverage_stays_eligible():
    at = (datetime.now().astimezone() - timedelta(minutes=5)).isoformat()
    row = Row(
        article_id=1, title="Запоріжжя: відкрили центр допомоги",
        raw_text="У Запоріжжі відкрили новий центр допомоги переселенцям.",
        final_text="У Запоріжжі відкрили центр допомоги",
        published_at=at,
    )
    current = {
        "title": "У Запоріжжі внаслідок атаки поранені двоє людей",
        "raw_text": "У Запоріжжі внаслідок атаки поранені двоє людей",
        "final_text": "Повідомили про поранених людей",
    }
    assert recent_community_incident_duplicate(Store([row]), 3, 2, current) == 0
