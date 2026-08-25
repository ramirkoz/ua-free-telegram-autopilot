from __future__ import annotations

from telegram_autopilot.rc38_policy import (
    _event_duplicate_fallback,
    compact_readability_issues,
    primary_topic,
    topic_balance_reject_reason,
)


def _row(article_id: int, title: str, body: str) -> dict[str, object]:
    return {
        "id": article_id,
        "title": title,
        "teaser_text": body,
        "event_summary": body,
        "full_article_uk": body,
        "raw_text": "",
    }


def test_rc38_catches_cross_source_nvidia_taiwan_china_event_duplicate() -> None:
    first = _row(
        101,
        "Nvidia senior manager linked to Supermicro scheme smuggling AI servers to China",
        "74 високопродуктивні сервери для ШІ дійшли до китайських клієнтів попри експортні обмеження США. "
        "Тайванська прокуратура висунула обвинувачення дев’ятьом людям, серед них менеджер Nvidia і працівники Supermicro. "
        "Ще 56 систем митниця зупинила через невідповідності документів.",
    )
    second_title = "Nine indicted by Taiwan over illegal export of Nvidia B300 GPUs to China"
    second_body = (
        "130 серверних систем із Nvidia B300 стали центром справи про незаконне вивезення чипів до Китаю. "
        "Окружна прокуратура Кілуна висунула обвинувачення дев’ятьом людям. "
        "За матеріалами справи, контроль Supermicro обходили через кілька ланок постачання на Тайвані."
    )
    match = _event_duplicate_fallback(second_title, second_body, [first])
    assert match is not None
    assert match.article_id == 101


def test_rc38_does_not_merge_unrelated_nvidia_stories() -> None:
    old = _row(
        201,
        "Nvidia unveils new workstation GPU for creators",
        "Nvidia представила нову професійну GPU для робочих станцій. Карта орієнтована на локальні AI-моделі та 3D-рендеринг.",
    )
    current_title = "Nvidia server export case leads to indictments in Taiwan"
    current_body = "На Тайвані дев’ятьом людям висунули обвинувачення у справі про незаконний експорт серверів Nvidia до Китаю."
    assert _event_duplicate_fallback(current_title, current_body, [old]) is None


def test_rc38_compact_gate_rejects_dense_four_paragraph_copy() -> None:
    body = "\n\n".join([
        "Перший абзац містить багато деталей про компанію, її плани, технологію та пояснення, які читачеві не потрібні для розуміння самої новини.",
        "Другий абзац додає ще більше контексту, цифр і технічних уточнень, хоча основну подію вже можна було пояснити значно коротше.",
        "Третій абзац знову розгортає передісторію та ще одну цитату, через що Telegram-пост починає нагадувати стислий реферат статті.",
        "Четвертий абзац завершує все додатковим узагальненням, яке не додає нового факту і лише збільшує щільність тексту для читача.",
    ])
    issues = compact_readability_issues(body)
    assert any("абзац" in issue for issue in issues)


def test_rc38_compact_gate_accepts_short_two_paragraph_news() -> None:
    body = (
        "Тайванська митниця зупинила партію AI-серверів, яку намагалися вивезти до Китаю в обхід експортних обмежень. "
        "У справі обвинувачують дев’ятьох людей.\n\n"
        "Слідство пов’язує схему з документами на сервери Nvidia та ланцюгом постачання через кілька компаній. Частина обладнання встигла дійти до клієнтів раніше."
    )
    assert compact_readability_issues(body) == ()


def test_rc38_topic_balance_caps_space_feed() -> None:
    article = {"title": "New SpaceX launch sends another satellite batch to orbit", "raw_text": "SpaceX Falcon rocket launch into orbit."}
    recent = [
        _row(1, "NASA ISS spacewalk replaces antenna", "Астронавти NASA вийшли у відкритий космос на МКС."),
        _row(2, "Perseid meteor shower could intensify", "Персеїди можуть стати активнішими через вплив Юпітера."),
        _row(3, "Falcon 9 booster sets reuse record", "SpaceX готує рекордний повторний політ Falcon 9."),
        _row(4, "Microsoft Teams changes bot controls", "Teams отримав нові правила для зовнішніх ботів."),
        _row(5, "Hyundai launches Ioniq 3", "Hyundai представила новий електромобіль."),
        _row(6, "South Korea startup platform breach", "Витік даних стався через відкритий ключ."),
        _row(7, "Redfin returns after FTC settlement", "FTC відновила конкуренцію на ринку оренди."),
        _row(8, "Homebrew LED project", "Ютубер зробив світлодіоди у домашній майстерні."),
    ]
    reason = topic_balance_reject_reason(article, recent)
    assert reason.startswith("TOPIC_BALANCE_SKIP")


def test_rc38_topic_balance_keeps_critical_cyber_even_if_topic_busy() -> None:
    article = {"title": "CVE-2026-99999 is actively exploited", "raw_text": "Critical vulnerability actively exploited in attacks."}
    recent = [_row(i, f"Security breach {i}", "Кібербезпека та уразливість у корпоративній системі.") for i in range(1, 9)]
    assert primary_topic(article) == "cyber"
    assert topic_balance_reject_reason(article, recent) == ""
