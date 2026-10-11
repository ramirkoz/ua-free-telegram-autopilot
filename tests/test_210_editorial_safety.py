from types import SimpleNamespace

import pytest

from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode
from telegram_autopilot.v2.editorial import hard_editorial_reject, deterministic_monitoring_exclusion


def monitor():
    return ChannelConfig(id=3, name="ЗАПОРІЖЖЯ | ГРОМАДИ", telegram_chat_id="@community", mode=ChannelMode.MONITORING)


def editor():
    return ChannelConfig(id=1, name="CTRL+UA", telegram_chat_id="@editor", mode=ChannelMode.EDITORIAL)


def article(source, title=""):
    return {"raw_text": source, "title": title, "source_name": "Source"}


@pytest.mark.parametrize("raw", [
    "Гучно!!!", "Ще", "Знову", "КАБи", "❤️ Запоріжжя", "💯",
    "Молнія на Хортиці", "Пуски КАБів попередньо в бік Оріхова",
    "Вибухи у Запоріжжі", "КАБи в бік Вільнянська",
])
def test_monitoring_context_never_invented(raw):
    code = hard_editorial_reject(monitor(), article(raw), "Офіційне повідомлення про відновлення послуг")
    assert code in {"MONITORING_CONTEXT_MISSING", "MONITORING_LIVE_ALERT"}
    assert deterministic_monitoring_exclusion(monitor(), article(raw))


@pytest.mark.parametrize("raw", [
    "11 жовтня у Запоріжжі оголошено День жалоби. У міській раді підтвердили відповідне рішення.",
    "Розівська військова адміністрація уклала меморандум про безкоштовну правову допомогу ВПО громади. Звернення за номером 0958067950.",
    "За даними Запорізької міської ради, житло 518 людей постраждало внаслідок нічної атаки. Дані внесено до програми допомоги.",
])
def test_verified_nonlive_community_information_not_blocked(raw):
    assert hard_editorial_reject(monitor(), article(raw), "Достовірний текст для громади") == ""


@pytest.mark.parametrize("text", [
    "**Готовий текст поста:** У Запоріжжі працюють установи.",
    "Джерело додасть footer. Читати у виданні.",
    "Немає нового повідомлення для публікації.",
    "Це не підходить для публікації в каналі.",
    "НЕ ПУБЛІКУВАТИ: джерело не містить деталей.",
    "За наданим контекстом цього неможливо визначити.",
])
def test_model_meta_never_published_any_channel(text):
    row = article("Дослідники оприлюднили нову технологію.")
    assert hard_editorial_reject(editor(), row, text) == "EDITORIAL_META_LEAK"
    assert hard_editorial_reject(monitor(), row, text) == "EDITORIAL_META_LEAK"


def test_editorial_scope_not_randomly_restricted_by_monitoring_rules():
    assert hard_editorial_reject(editor(), article("Пуски КАБів у напрямку міста"), "Технічна стаття про системи") == ""
