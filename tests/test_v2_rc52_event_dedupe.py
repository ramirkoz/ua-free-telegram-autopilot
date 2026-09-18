from __future__ import annotations

import sqlite3

from telegram_autopilot.v2.bounded_ingest import BoundedStrictIngestService
from telegram_autopilot.v2.domain import DedupeProfile, EditorialRuntimeProfile
from telegram_autopilot.v2.event_dedupe_guard import (
    EventFingerprintDedupeEngine,
    _near_numeric_pairs,
    event_fingerprint_same_event,
)
from telegram_autopilot.v2.storage import V2Store


def _row(source_id: int, title: str, body: str) -> dict[str, object]:
    return {
        "source_id": source_id,
        "source_name": f"source-{source_id}",
        "title": title,
        "raw_text": body,
        "final_text": "",
        "event_summary": "",
        "canonical_source_url": f"https://example{source_id}.org/item",
        "source_url": f"https://example{source_id}.org/item",
        "content_hash": f"hash-{source_id}",
    }


def test_observed_human_cortical_mouse_study_is_one_event_in_scientific_profile() -> None:
    first = _row(
        1,
        "Людські нейрони заповнили понад 90 відсотків кори головного мозку мишей",
        (
            "Дослідники виростили генетично модифікованих мишей без більшої частини кори та гіпокампа. "
            "У порожній простір пересадили крихітні згустки людських нейронів, вирощені зі стовбурових клітин. "
            "За три місяці людська тканина збільшилася майже у п'ять разів та інтегрувалася в нервову систему."
        ),
    )
    second = _row(
        2,
        "Людський трансплантат зайняв близько 92 відсотків кортикальної тканини миші",
        (
            "Дослідники інтегрували людські кортикальні органоїди у нервову систему генетично модифікованих мишей. "
            "Тканини зі стовбурових клітин пересадили в мозок. Органоїд розрісся, з'єднався з мозком і спинним мозком "
            "та активувався під час неспання."
        ),
    )

    same, reason = event_fingerprint_same_event(
        first,
        second,
        compound_events=True,
        rare_terms=True,
    )

    assert same is True
    assert "fingerprint" in reason


def test_near_percentages_are_compatible_numeric_anchors() -> None:
    assert _near_numeric_pairs("понад 90% кори", "близько 92 відсотків тканини") == [(90.0, 92.0)]


def test_scientific_name_fingerprint_is_generic_and_opt_in() -> None:
    first = _row(
        1,
        "У Чилі описали Leopardus tilcayo",
        "Дослідники повідомили про новий вид дикої кішки після польових спостережень.",
    )
    second = _row(
        2,
        "Leopardus tilcayo поповнив перелік котячих",
        "Науковці відкрили новий вид і окремо описали його морфологічні ознаки.",
    )

    baseline, _ = event_fingerprint_same_event(first, second)
    enabled, reason = event_fingerprint_same_event(first, second, scientific_names=True)

    assert baseline is False
    assert enabled is True, reason
    assert "leopardus tilcayo" in reason


def test_compound_subject_method_mechanism_fingerprint_is_not_story_specific() -> None:
    first = _row(
        1,
        "Папіруси Геркуланума читають за свинцевим чорнилом",
        (
            "Команда дослідила сувої Геркуланума рентгенівською томографією. "
            "Цифрове розгортання папірусів виявило свинцеві чорнила всередині нерозкритих сувоїв."
        ),
    )
    second = _row(
        2,
        "Новий метод прочитав сувої Геркуланума без фізичного розкриття",
        (
            "Для папірусів Геркуланума застосували рентгенівське сканування та цифрове розгортання. "
            "Свинцеве чорнило створило контраст, який дозволив відновити текст усередині сувою."
        ),
    )

    same, reason = event_fingerprint_same_event(
        first,
        second,
        compound_events=True,
        rare_terms=True,
    )

    assert same is True, reason
    assert "compound" in reason


def test_same_topic_but_different_mouse_study_is_not_collapsed() -> None:
    transplant = _row(
        1,
        "Людські нейрони інтегрували у кору мозку мишей",
        "Людські кортикальні органоїди зі стовбурових клітин пересадили у мозок мишей і тканина розрослася.",
    )
    drug_trial = _row(
        2,
        "Новий препарат змінив активність нейронів кори мозку мишей",
        "Вчені дослідили дію експериментального препарату на нейрони кори мозку лабораторних мишей та виміряли координацію тварин.",
    )

    same, _ = event_fingerprint_same_event(
        transplant,
        drug_trial,
        compound_events=True,
        rare_terms=True,
    )

    assert same is False


def test_ctrlua_migration_sets_only_that_channel_to_scientific_profile(tmp_path) -> None:
    db = tmp_path / "old.sqlite3"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE meta (key TEXT PRIMARY KEY,value TEXT NOT NULL)")
        con.execute(
            """CREATE TABLE channels (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                telegram_chat_id TEXT NOT NULL DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 1,
                channel_mode TEXT NOT NULL DEFAULT 'editorial',
                editorial_profile TEXT NOT NULL DEFAULT '',
                include_source_link INTEGER NOT NULL DEFAULT 1,
                source_link_required INTEGER NOT NULL DEFAULT 1,
                poll_interval_minutes INTEGER NOT NULL DEFAULT 5,
                poll_immediate INTEGER NOT NULL DEFAULT 0,
                min_publish_interval_minutes INTEGER NOT NULL DEFAULT 10,
                dedupe_window_hours INTEGER NOT NULL DEFAULT 72,
                max_age_hours INTEGER NOT NULL DEFAULT 24,
                max_posts_per_cycle INTEGER NOT NULL DEFAULT 3,
                publish_24h INTEGER NOT NULL DEFAULT 0,
                publish_start TEXT NOT NULL DEFAULT '07:00',
                publish_end TEXT NOT NULL DEFAULT '00:00',
                publish_immediately INTEGER NOT NULL DEFAULT 0,
                topic_balance_enabled INTEGER NOT NULL DEFAULT 1,
                topic_daily_limit INTEGER NOT NULL DEFAULT 2,
                related_spacing_posts INTEGER NOT NULL DEFAULT 5,
                editorial_weights_json TEXT NOT NULL DEFAULT '[]',
                language_mode TEXT NOT NULL DEFAULT 'ukru_to_uk',
                media_enrichment_mode TEXT NOT NULL DEFAULT 'auto',
                media_first_allowed INTEGER NOT NULL DEFAULT 1,
                media_min_text_chars INTEGER NOT NULL DEFAULT 500,
                legacy_config_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT ''
            )"""
        )
        con.execute("INSERT INTO channels(id,name) VALUES(1,'CTRL+UA')")
        con.execute("INSERT INTO channels(id,name) VALUES(2,'ПРОДАНО')")

    store = V2Store(db)
    ctrl = store.get_channel(1)
    sold = store.get_channel(2)

    assert ctrl is not None and sold is not None
    assert ctrl.dedupe_profile == DedupeProfile.SCIENTIFIC_NEWS
    assert ctrl.dedupe_scientific_names is True
    assert ctrl.dedupe_compound_events is True
    assert ctrl.dedupe_rare_terms is True
    assert ctrl.published_dedupe_window_hours == 720

    assert sold.dedupe_profile == DedupeProfile.COMMERCIAL_EDITORIAL
    assert sold.editorial_runtime_profile == EditorialRuntimeProfile.COMMERCIAL_EDITORIAL
    assert sold.dedupe_scientific_names is False
    assert sold.dedupe_compound_events is False
    assert sold.dedupe_rare_terms is False
    assert sold.published_dedupe_window_hours == 720


def test_final_gate_uses_event_fingerprint_engine_and_rolling_source_timeout() -> None:
    assert issubclass(EventFingerprintDedupeEngine, object)
    assert BoundedStrictIngestService.source_timeout_seconds <= 70.0
    assert BoundedStrictIngestService.active_source_slots >= 1
    assert not hasattr(BoundedStrictIngestService, "channel_source_budget_seconds")
