"""Real v2.2.13 21 Oct 18:46 operator incident, regression #199."""
from __future__ import annotations
from types import SimpleNamespace

import pytest

from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode, ChannelPolicy
from telegram_autopilot.v2.publication_safety import is_ai_rejection_text
from telegram_autopilot.v2.editorial import (
    hard_editorial_reject, prepublish_quality_issues, validate_writer_output
)
from telegram_autopilot.v2.monitoring_civic_quality import civic_relevance_exclusion


SCREENSHOT = (
    "Джерело не містить інформації, що стосується Запорізької "
    "області, її громад, місцевої влади, послуг чи життя мешканців "
    "регіону. Тому пост не створюється."
)
LEADER_CLIP = (
    '🚧 Посланець Трампа Віткофф розповідав Путіну: '
    '"Ви теж гуманіст, пане, і я це високо ціную". '
    "На відео дипломатична зустріч."
)
MUNICIPAL_EVENT = (
    "Запорізька міська рада 22 жовтня проводить зустріч щодо "
    "укриттів та шкіл для мешканців Запоріжжя."
)


def monitor():
    return ChannelConfig(
        id=17, name="Будь-який моніторинговий канал", telegram_chat_id="@community",
        mode=ChannelMode.MONITORING,
        policy=ChannelPolicy(channel_id=17,rejection_rules="[LIVE_NOW_RC96]"),
    )


def editorial():
    return ChannelConfig(id=2,name="Commercial editor",telegram_chat_id="@editor",mode=ChannelMode.EDITORIAL)


def row(source):
    return {
        "id":71994, "channel_id":17,
        "title":source[:90], "raw_text":source,
        "source_url":"https://t.me/zaborzp/155017",
    }


@pytest.mark.parametrize("text",[
    SCREENSHOT,
    "Джерело не містить інформації, що стосується громад. Тому пост не створюється.",
    "Джерело не надає фактів щодо місцевих послуг. Отже пост не публікується.",
    "Відповідь: інформації про подію немає; не публікувати цей матеріал.",
    "Цей матеріал не відповідає тематиці каналу; пост не буде створено.",
    "No post will be created because the source does not contain relevant local information.",
])
def test_ai_refusal_cannot_reach_telegram_even_without_label(text):
    assert is_ai_rejection_text(text), text
    assert hard_editorial_reject(editorial(),row(MUNICIPAL_EVENT),text) in {
        "AI_REJECTION_LEAK_BLOCKED","EDITORIAL_META_LEAK",
    }
    assert hard_editorial_reject(monitor(),row(MUNICIPAL_EVENT),text) in {
        "AI_REJECTION_LEAK_BLOCKED","EDITORIAL_META_LEAK",
    }


def test_real_screenshot_blocks_writer_and_stale_ready_prepublication():
    with pytest.raises(ValueError, match="AI_REJECTION_LEAK_BLOCKED"):
        validate_writer_output(row(MUNICIPAL_EVENT),SCREENSHOT,min_chars=60,max_chars=800)
    result=prepublish_quality_issues(monitor(),row(MUNICIPAL_EVENT),SCREENSHOT)
    assert any("AI_REJECTION_LEAK_BLOCKED" in s for s in result)


@pytest.mark.parametrize("text",[
    "У Запоріжжі відкрили виставку «Чому пост не створюється». Автор презентував цифрові роботи.",
    "«Пост не створюється», пояснив редактор під час обговорення нової онлайн-платформи.",
    "Журналісти розповіли про скаргу мешканців: у громаді немає достатньо відомостей про послуги.",
    "У Запоріжжі підтвердили пошкодження будинків та опублікували перелік адрес для допомоги.",
])
def test_reportage_and_attributed_refusal_quotes_not_flagged(text):
    assert not is_ai_rejection_text(text), text


def test_actual_foreign_leader_clip_from_operator_source_is_not_local_news():
    source=row(LEADER_CLIP)
    assert civic_relevance_exclusion(monitor(),source).startswith("MONITORING_OFF_TOPIC_GLOBAL_CLIP")
    assert hard_editorial_reject(monitor(),source,"Дипломатичні переговори лідерів") .startswith("MONITORING_OFF_TOPIC_GLOBAL_CLIP")


@pytest.mark.parametrize("source",[
    MUNICIPAL_EVENT,
    "Президент США Трамп оголосив допомогу постраждалим мешканцям Запоріжжя у програмі відновлення житла.",
    "Віткофф та Путін згадували енергетичну ситуацію в Запоріжжі після атаки, яка пошкодила школу.",
    "У Запоріжжі провели культурну виставку відео про історичні події громади.",
])
def test_legitimate_local_event_survives_foreign_policy_filter(source):
    assert not civic_relevance_exclusion(monitor(),row(source))


def test_other_channel_not_affected_by_locality_gate():
    assert not civic_relevance_exclusion(editorial(),row(LEADER_CLIP))


def test_publication_guard_before_media_is_present():
    # Regression-proof binding check: operator reported media was sent with a
    # selector rejection. The publisher must check before its first media API.
    import inspect
    from telegram_autopilot.v2.publisher import Publisher
    source=inspect.getsource(Publisher.publish_one)
    assert 'gate="before_media"' in source
    assert source.index('gate="before_media"') < source.index("bundle")
