from __future__ import annotations

import json
from pathlib import Path

from telegram_autopilot.v2.publisher import _strip_all_publication_links
from telegram_autopilot.v2.storage import V2Store, now_iso


def _store(tmp_path: Path) -> V2Store:
    store = V2Store(tmp_path / "rc86.sqlite3")
    stamp = now_iso()
    with store.connect() as con:
        con.execute(
            """INSERT INTO channels(id,name,telegram_chat_id,channel_mode,created_at,updated_at)
               VALUES(1,'TEST','@test','monitoring',?,?)""",
            (stamp, stamp),
        )
        con.execute("INSERT INTO channel_policies(channel_id,updated_at) VALUES(1,?)", (stamp,))
        con.execute(
            """INSERT INTO sources(id,channel_id,kind,name,url,enabled,priority,legacy_config_json)
               VALUES(1,1,'telegram','ЗаБор Запоріжжя','https://t.me/zaborzp',1,100,'{}')"""
        )
    return store


def test_strip_all_publication_links_removes_zabor_promos() -> None:
    text = (
        "Кіберполіція попереджає про шахрайські кол-центри.\n\n"
        "Детальніше: https://zabor.zp.ua/new/example\n\n"
        "Деталі/реєстрація: https://t.me/zabornews_bot\n\n"
        "[Корисна назва](https://example.test/page)"
    )
    cleaned = _strip_all_publication_links(text)
    assert "http://" not in cleaned
    assert "https://" not in cleaned
    assert "Детальніше" not in cleaned
    assert "Деталі/реєстрація" not in cleaned
    assert "Корисна назва" in cleaned


def test_source_policy_is_operator_editable(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert store.source_strip_body_links(1) is False
    store.set_source_strip_body_links(1, True)
    assert store.source_strip_body_links(1) is True
    store.set_source_strip_body_links(1, False)
    assert store.source_strip_body_links(1) is False




from telegram_autopilot.v2.semantic_dedupe import semantic_same_event


def test_cross_source_same_evacuation_attack_is_duplicate() -> None:
    first = {
        "source_id": 101,
        "title": "Росіяни знову атакували евакуаційну команду на Запоріжжі",
        "raw_text": "Під обстріл потрапили волонтери. За словами Ігоря Піліпушка, ніхто не постраждав.",
        "final_text": (
            "Росіяни знову атакували евакуаційну команду на Запоріжжі. "
            "Під обстріл потрапили волонтери, які допомагають людям виїхати з небезпечних районів. "
            "За словами волонтера Ігоря Піліпушка, ніхто з команди не постраждав. "
            "Попри атаку, евакуаційники продовжили роботу та забрали людей, які чекали на порятунок."
        ),
        "source_published_at": "2026-09-25T17:39:00+03:00",
        "discovered_at": "2026-09-25T17:39:00+03:00",
        "source_name": "5 РЕДАКЦІЯ",
    }
    second = {
        "source_id": 202,
        "title": "Російські військові атакували евакуаційну команду на Запоріжжі",
        "raw_text": "Команда продовжила роботу та забрала людей. Волонтер Ігор Піліпушко повідомив, що постраждалих немає.",
        "final_text": (
            "Російські військові атакували евакуаційну команду на Запоріжжі. "
            "За словами волонтера Ігоря Піліпушка, ніхто не постраждав. "
            "Команда продовжила роботу та забрала людей, які чекали на евакуацію."
        ),
        "source_published_at": "2026-09-25T17:57:00+03:00",
        "discovered_at": "2026-09-25T17:57:00+03:00",
        "source_name": "БЕЗ БАЙДИ",
    }
    same, reason = semantic_same_event(first, second)
    assert same is True
    assert (
        reason.startswith("breaking-incident cluster")
        or reason.startswith("high-confidence final-text event duplicate")
    )


def test_similar_but_later_evacuation_event_is_not_forced_duplicate() -> None:
    first = {
        "source_id": 101,
        "title": "Евакуаційна команда потрапила під обстріл на Запоріжжі",
        "raw_text": "Волонтери продовжили евакуацію людей.",
        "final_text": "Евакуаційна команда потрапила під обстріл на Запоріжжі. Волонтери продовжили роботу.",
        "source_published_at": "2026-09-25T08:00:00+03:00",
        "discovered_at": "2026-09-25T08:00:00+03:00",
        "source_name": "A",
    }
    later = {
        "source_id": 202,
        "title": "Увечері евакуаційна команда знову потрапила під обстріл",
        "raw_text": "Під час нового вечірнього виїзду волонтери потрапили під обстріл.",
        "final_text": "Увечері евакуаційна команда знову потрапила під обстріл. Волонтери продовжили роботу.",
        "source_published_at": "2026-09-25T20:30:00+03:00",
        "discovered_at": "2026-09-25T20:30:00+03:00",
        "source_name": "B",
    }
    same, _ = semantic_same_event(first, later)
    assert same is False
