"""2.3.22 operator regression pack: NO classifieds and no trade-magazine focus.

All in-memory. No operator SQLite, network, paid AI or Telegram delivery.
"""
from __future__ import annotations

from contextlib import contextmanager
import sqlite3
from types import SimpleNamespace

from telegram_autopilot.v2.domain import ChannelMode, ChannelConfig, ChannelPolicy
from telegram_autopilot.v2.editorial import (
    EditorialEngine, hard_editorial_reject, prepublish_quality_issues,
    _rc111_prepare_candidate,
)
from telegram_autopilot.v2.monitoring_source_scope_2317 import (
    monitoring_source_scope_reason_2317,
)
from telegram_autopilot.v2.private_document_contact_2322 import no_announcement_reason_2322
from telegram_autopilot.v2.commercial_sources_2322 import (
    apply_commercial_sources_2322, RETIRE_EXACT, PRIORITIZE_EXACT, FRESH,
)


def ch(mode=ChannelMode.MONITORING):
    return ChannelConfig(
        id=3, name="Регіональна стрічка", telegram_chat_id="-100123",
        mode=mode,
        policy=ChannelPolicy(channel_id=3, rejection_rules="[LIVE_NOW_RC96]"),
    )


def art(title, body, *, url="https://t.me/news/123"):
    return {
        "id": 2322, "title": title, "raw_text": body,
        "source_url": url, "canonical_source_url": url,
        "source_name": "Джерело",
    }


SAMPLES = (
    art("Знайшли документи",
        "У Запоріжжі знайшли паспорт та ключі. Телефонуйте 098 000 00 00 для повернення."),
    art("Чиї загублені речі",
        "Знайдені документи на ім’я приватної особи у дворі лікарні."),
    art("У дворі залишили собак",
        "Біля лікарні залишили собак. Контакт приватної особи: 098 000 00 00."),
    art("Оголошення", "Продам холодильник і меблі, пишіть у приватні повідомлення."),
    art("Оголошення про роботу", "Шукаємо працівників до невеликої кав'ярні. Нові вакансії."),
    art("Відкрита реєстрація", "Запрошуємо всіх на фестиваль. Реєстрація на сайті."),
    art("Великий розпродаж", "Знижки на електроніку, встигніть купуйте до 60% дешевше."),
    art("Гарного дня", "Вітаємо з днем працівників культури. Бажаємо всім гарного дня!"),
)


def test_each_standalone_announcement_gets_blocked_without_ai():
    editor = object.__new__(EditorialEngine)
    editor.gateway = SimpleNamespace(
        run=lambda *a, **kw: (_ for _ in ()).throw(
            AssertionError("source-only notice must not consume AI")
        )
    )
    for row in SAMPLES:
        code = no_announcement_reason_2322(row)
        assert code, row["title"]
        output = editor.select(ch(), row)
        assert str(output.decision).upper().endswith("REJECT"), row["title"]
        assert hard_editorial_reject(ch(), row, "Повідомлення опубліковано. Джерело додається.") == code


def test_real_civic_news_not_blocked_as_notice():
    stories = (
        art("У Запоріжжі відкрили нове укриття",
            "Вчора у Запоріжжі завершили облаштування укриття біля школи. "
            "Рятувальники перевірили доступ та підписали акт готовності."),
        art("Міська рада змінила маршрути",
            "У Запоріжжі міськрада повідомила про зміни руху тролейбуса №3. "
            "Новий графік діє із завтрашнього дня через ремонт дороги."),
        art("У Запоріжжі стартувала нова програма підтримки ВПО",
            "Соціальний центр у Запоріжжі почав надавати психологічну підтримку "
            "переселенцям. Перші родини звернулися за послугою."),
    )
    for row in stories:
        assert not no_announcement_reason_2322(row), row["title"]
        # Other unrelated source-provenance rules may still reject a
        # synthetic Telegram channel; this test checks announcement scope only.


def test_specific_nationwide_military_paperwork_scope_only():
    national = art(
        "Міноборони змінило правила військового обліку",
        "Міноборони затвердило наказ щодо правил військового обліку. "
        "Документ змінює облік персоналу військових підрозділів.",
    )
    local = art(
        "У Запоріжжі обговорили військовий облік в громаді",
        "У Запоріжжі місцева рада запровадила новий графік прийому "
        "жителів. Міноборони оновило правила військового обліку.",
    )
    assert monitoring_source_scope_reason_2317(ch(), national) == (
        "MONITORING_NONLOCAL_MILITARY_PAPERWORK_2322"
    )
    assert monitoring_source_scope_reason_2317(ch(), local) == ""
    assert monitoring_source_scope_reason_2317(ch(ChannelMode.EDITORIAL), national) == ""


def test_duplicate_source_url_removed_before_paid_writer_validation():
    row = art(
        "У Запоріжжі відкрили громадський простір",
        "У Запоріжжі відкрили громадський простір. Понад сто місцевих "
        "відвідали нову бібліотеку.",
        url="https://t.me/localnews/77",
    )
    raw = (
        "У Запоріжжі відкрили новий громадський простір. "
        "Нову бібліотеку відвідали місцеві жителі.\n\n"
        "Джерело: https://t.me/localnews/77"
    )
    prepared = _rc111_prepare_candidate(
        ch(), row, raw, hard_max_chars=900, min_chars=80
    )
    assert "https://t.me/localnews/77" not in prepared
    assert "Джерело:" not in prepared
    assert "новий громадський простір" in prepared


class FakeStore:
    def __init__(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
          CREATE TABLE channels(id INTEGER PRIMARY KEY, channel_mode TEXT,
                                 editorial_runtime_profile TEXT);
          CREATE TABLE sources(
             id INTEGER PRIMARY KEY,channel_id INTEGER,name TEXT,url TEXT,
             kind TEXT,enabled INTEGER,initialized INTEGER,priority INTEGER,
             legacy_config_json TEXT DEFAULT '{}'
          );
          CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT);
          INSERT INTO channels VALUES(2,'editorial','commercial_editorial');
          INSERT INTO channels VALUES(7,'editorial','commercial_editorial');
          INSERT INTO channels VALUES(3,'monitoring','monitoring');
        """)
        self.db.executemany(
            "INSERT INTO sources(channel_id,name,url,kind,enabled,initialized,priority) "
            "VALUES(?,?,?,?,?,?,?)",
            [
                (2, "Yanko Design", "https://www.yankodesign.com/feed/", "rss", 1, 1, 18),
                (2, "Creative Bloq", "https://www.creativebloq.com/feeds.xml", "rss", 1, 1, 22),
                (2, "Muse by Clio", "https://musebyclios.com/feed/", "rss", 1, 1, 14),
                (2, "Campaign Brief", "https://campaignbrief.com/feed/", "rss", 1, 1, 15),
                (2, "The Dieline", "https://thedieline.com/feed/", "rss", 1, 1, 11),
                (2, "Colossal", "https://www.thisiscolossal.com/feed/", "rss", 1, 1, 30),
                (2, "My Custom Art", "https://custom.example/feed", "rss", 1, 1, 3),
                (7, "User Custom", "https://custom.example/other", "rss", 1, 1, 10),
                (3, "Local Source", "https://t.me/example", "telegram", 1, 1, 50),
            ],
        )
        self.db.commit()

    @contextmanager
    def transaction(self):
        yield self.db


def test_consumer_portfolio_disables_only_exact_trade_and_preserves_user_sources():
    store = FakeStore()
    before = store.db.execute("SELECT count(*) FROM sources").fetchone()[0]
    first = apply_commercial_sources_2322(store)
    assert first["channels"][0]["status"] == "applied"
    assert first["channels"][1]["status"] == "custom_preserved"
    for name in ("Muse by Clio", "Campaign Brief", "The Dieline"):
        assert store.db.execute(
            "SELECT enabled FROM sources WHERE channel_id=2 AND name=?",
            (name,),
        ).fetchone()[0] == 0
    assert store.db.execute(
        "SELECT enabled FROM sources WHERE name='My Custom Art'"
    ).fetchone()[0] == 1
    assert store.db.execute(
        "SELECT priority FROM sources WHERE name='Yanko Design'"
    ).fetchone()[0] == 12
    new = store.db.execute(
        "SELECT name,url,enabled,initialized FROM sources WHERE channel_id=2 "
        "AND name IN ('My Modern Met','Laughing Squid')"
    ).fetchall()
    assert len(new) == 2 and all(r["enabled"] == 1 and r["initialized"] == 0 for r in new)
    assert store.db.execute("SELECT count(*) FROM sources").fetchone()[0] == before + 2
    assert apply_commercial_sources_2322(store)["channels"][0]["status"] == "already_applied"
    assert store.db.execute("SELECT count(*) FROM sources").fetchone()[0] == before + 2
    assert store.db.execute("SELECT enabled FROM sources WHERE channel_id=3").fetchone()[0] == 1
