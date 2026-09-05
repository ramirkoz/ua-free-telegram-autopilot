from __future__ import annotations

import json

from telegram_autopilot import rc45_policy as rc45
from telegram_autopilot import rc68_editorial_value as rc68
from telegram_autopilot import rc69_media_language as rc69


UA_TEXT = (
    "Це український матеріал про нову технологію. Дослідники пояснили, як вона працює і чому результат важливий. "
    "У роботі є нові дані, які можуть допомогти краще зрозуміти процес. Автори також описали обмеження дослідження. "
    "Після перевірки результатів команда планує продовжити експерименти, але поки не робить сильніших висновків."
)
RU_TEXT = (
    "Это российский текст о новой технологии, и исследователи объяснили, как она работает. "
    "После проверки результатов команда сообщила, что эффект может быть полезен для дальнейших экспериментов. "
    "Исследование пока не доказывает практическую пользу, но авторы считают, что данные нужно проверить еще раз. "
    "Для этого будут проведены дополнительные испытания, которые должны показать, насколько результат устойчив."
)
EN_TEXT = (
    "This is an English source about a new technology and the researchers explain how it works. "
    "The study reports new data and says the result could help future experiments. The authors also describe the limits "
    "of the work and say more testing will be needed before the system can be used in practice."
)


def test_rc69_accepts_all_four_channel_language_directions() -> None:
    assert rc69.accepts_input(rc45.DIRECTION_EN_TO_UK, EN_TEXT)
    assert rc69.accepts_input(rc45.DIRECTION_UKRU_TO_EN, UA_TEXT)
    assert rc69.accepts_input(rc69.DIRECTION_UK_TO_UK, UA_TEXT)
    assert rc69.accepts_input(rc69.DIRECTION_RU_TO_UK, RU_TEXT)


def test_rc69_ru_to_uk_does_not_accept_ukrainian_prose() -> None:
    assert rc69.looks_russian(RU_TEXT)
    assert not rc69.looks_russian(UA_TEXT)
    assert not rc69.accepts_input(rc69.DIRECTION_RU_TO_UK, UA_TEXT)


class _MediaDB:
    def __init__(self, row: dict[str, object], media: list[str]):
        self.row = row
        self.media = media
        self.updated: dict[str, object] = {}

    def get_article(self, article_id: int):
        assert article_id == int(self.row["id"])
        current = dict(self.row)
        current.update(self.updated)
        return current

    def media_urls(self, _row):
        return list(self.media)

    def update_article(self, article_id: int, **fields):
        assert article_id == int(self.row["id"])
        self.updated.update(fields)


class _Service:
    def __init__(self, db):
        self.db = db
        self.audit = []

    def _audit(self, *args, **kwargs):
        self.audit.append((args, kwargs))


class _Channel:
    id = 7
    media_enrichment_mode = rc69.MEDIA_ENRICH_AUTO
    media_first_allowed = True
    media_min_text_chars = 500


def _thin_video_row() -> dict[str, object]:
    return {
        "id": 44,
        "title": "Guinness turns one word into its new campaign idea",
        "raw_text": "Guinness has released a new campaign. Watch the film below.",
        "article_layout_json": json.dumps(
            {
                "version": 5,
                "blocks": [
                    {
                        "type": "media",
                        "kind": "iframe",
                        "url": "https://www.youtube.com/embed/abc123",
                        "caption": "The new Guinness film built around the word lovely",
                        "alt": "Guinness campaign film",
                    }
                ],
            }
        ),
        "media_enrichment_text": "",
    }


def test_rc69_media_evidence_uses_layout_and_video_metadata(monkeypatch) -> None:
    row = _thin_video_row()
    db = _MediaDB(row, ["iframe|https://www.youtube.com/embed/abc123"])
    monkeypatch.setattr(
        rc69,
        "_oembed_metadata",
        lambda _url: ["VIDEO TITLE: Guinness – A Lovely Day", "VIDEO AUTHOR/CHANNEL: Guinness"],
    )

    evidence, meta = rc69.build_media_evidence(db, row)

    assert "MEDIA CAPTION: The new Guinness film" in evidence
    assert "VIDEO TITLE: Guinness – A Lovely Day" in evidence
    assert "VIDEO AUTHOR/CHANNEL: Guinness" in evidence
    assert meta["video_urls"] == ["https://www.youtube.com/watch?v=abc123"]


def test_rc69_thin_media_first_article_is_enriched_before_selector(monkeypatch) -> None:
    row = _thin_video_row()
    db = _MediaDB(row, ["iframe|https://www.youtube.com/embed/abc123"])
    service = _Service(db)
    monkeypatch.setattr(rc69, "_oembed_metadata", lambda _url: ["VIDEO TITLE: Guinness – A Lovely Day"])

    rc69.enrich_article_for_media(service, _Channel(), 44)

    raw = str(db.updated["raw_text"])
    assert rc69.MEDIA_MARKER in raw
    assert "VIDEO TITLE: Guinness – A Lovely Day" in raw
    assert db.updated["media_enrichment_text"]
    assert db.updated["content_hash"]
    assert service.audit


def test_rc69_long_article_is_not_needlessly_enriched(monkeypatch) -> None:
    row = _thin_video_row()
    row["raw_text"] = "Long source sentence with actual reporting. " * 30
    db = _MediaDB(row, ["iframe|https://www.youtube.com/embed/abc123"])
    service = _Service(db)
    calls = []
    monkeypatch.setattr(rc69, "_oembed_metadata", lambda _url: calls.append(_url) or ["VIDEO TITLE: ignored"])

    rc69.enrich_article_for_media(service, _Channel(), 44)

    assert db.updated == {}
    assert calls == []


def test_rc69_strong_retellable_story_has_universal_second_value_lane() -> None:
    rc69._PREV["editorial_value_allowed"] = rc68.editorial_value_allowed
    data = {
        "novelty": 86,
        "consequence_or_insight": 30,
        "mechanism": 34,
        "reader_payoff": 76,
        "retellability": 84,
        "concrete_stakes": 28,
        "why_now": 62,
        "curiosity_only": True,
    }
    allowed, code, score = rc69._editorial_value_allowed_rc69(data)
    assert allowed is True
    assert code == "strong_retellable_payoff"
    assert score >= 55


def test_rc69_weak_curiosity_still_rejected() -> None:
    rc69._PREV["editorial_value_allowed"] = rc68.editorial_value_allowed
    data = {
        "novelty": 70,
        "consequence_or_insight": 18,
        "mechanism": 20,
        "reader_payoff": 35,
        "retellability": 42,
        "concrete_stakes": 10,
        "why_now": 30,
        "curiosity_only": True,
    }
    allowed, _code, _score = rc69._editorial_value_allowed_rc69(data)
    assert allowed is False


def test_rc69_channel_fit_prompt_says_short_media_text_is_not_auto_reject() -> None:
    rc69._PREV["channel_fit_prompt"] = lambda _policy, _article, *, channel_id: "BASE"
    prompt = rc69._channel_fit_prompt_rc69(object(), _thin_video_row(), channel_id=0)
    assert "Тематичні слова самі по собі НЕ означають" in prompt
    assert "короткий текст статті САМ ПО СОБІ не є причиною reject" in prompt
    assert rc69.MEDIA_MARKER in prompt
