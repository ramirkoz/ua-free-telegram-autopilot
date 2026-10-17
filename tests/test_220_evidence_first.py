import json
from types import SimpleNamespace

from telegram_autopilot.v2.evidence_first import (
    assess_monitoring_media,
    assess_monitoring_source,
)
from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode, ChannelPolicy
from telegram_autopilot.v2.editorial import hard_editorial_reject, prepublish_quality_issues


def article(raw, *, media="[]", layout=None, title="", url="https://t.me/local/123"):
    return SimpleNamespace(
        raw_text=raw, title=title or raw, source_name="Редакція",
        source_url=url, media_json=media,
        article_layout_json=json.dumps(layout or {}, ensure_ascii=False),
    )


def channel():
    return ChannelConfig(id=3, name="ГРОМАДИ", telegram_chat_id="@test",
                         mode=ChannelMode.MONITORING,
                         policy=ChannelPolicy(monitoring_source_policy="connected_original"))


def test_real_husky_and_documents_are_separate_notices():
    a = article(
        "На вулиці Романтичній приблудився хаскі. "
        "Хто загубив папку з документами по вулиці Василя Сергієнка біля АТБ, "
        "звертайтесь за номером. Його шукають."
    )
    assert "MONITORING_MULTIPLE_UNRELATED_NOTICES" in assess_monitoring_source(a).reasons
    assert hard_editorial_reject(channel(), a) == "MONITORING_MULTIPLE_UNRELATED_NOTICES"


def test_rszv_one_liner_cannot_be_presented_as_verified_aftermath():
    a = article("РСЗВ вдарило по Юр'ївці.")
    assert "MONITORING_UNVERIFIED_ATTACK_OUTCOME" in assess_monitoring_source(a).reasons
    assert hard_editorial_reject(channel(), a) == "MONITORING_UNVERIFIED_ATTACK_OUTCOME"


def test_ai_cannot_invent_no_information_received():
    a = article("У селі сталася дорожньо-транспортна пригодація. Рух транспорту ускладнений.")
    decision = assess_monitoring_source(a, final_text="Інформація про наслідки наразі не надходила.")
    assert "MONITORING_UNSUPPORTED_ABSENCE_CLAIM" in decision.reasons


def test_video_cue_without_bound_telegram_media_is_blocked():
    a = article(
        "Після зустрічі гостей розпочалася урочиста частина свята. "
        "Дивіться друге відео серії.",
        layout={"telegram": {"message_ids": ["14790"]}},
    )
    assert "MONITORING_VIDEO_ATTACHMENT_UNBOUND" in assess_monitoring_media(a).reasons
    assert "MONITORING_VIDEO_ATTACHMENT_UNBOUND" in prepublish_quality_issues(
        channel(), a, "У громаді відбулося свято. Дивіться друге відео серії."
    )


def test_valid_telegram_news_and_attached_video_not_suppressed():
    a = article("У громаді провели арттерапевтичний захід для молоді. "
                "Участь взяли представники місцевої адміністрації.")
    assert assess_monitoring_source(a).allowed
    assert assess_monitoring_media(a).allowed
    b = article("Дивіться відео зі святкування.", media='[{"url": "https://t.me/video"}]')
    assert assess_monitoring_media(b).allowed


def test_confirmed_aftermath_with_damage_is_not_live_one_liner():
    a = article("Після обстрілу рятувальники підтвердили пошкодження трьох будинків.")
    assert assess_monitoring_source(a).allowed


def test_photo_or_video_poster_cannot_replace_required_video():
    image = article("Дивіться відео із заходу.",
                    media='["https://example.org/preview.jpg"]')
    assert "MONITORING_VIDEO_ATTACHMENT_UNBOUND" in assess_monitoring_media(image).reasons
    pending = article("Дивіться відео із заходу.", media="[]",
                      layout={"telegram": {"video_attachment_seen": True}})
    assert assess_monitoring_media(pending).reasons == ("MONITORING_VIDEO_PENDING",)
