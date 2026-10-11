from types import SimpleNamespace
from telegram_autopilot.v2.editorial import _monitoring_safety_exclusion, _EDITORIAL_META_LEAK


def article(text: str):
    return SimpleNamespace(raw_text=text, title=text)


def test_210_reject_incomplete_live_sources():
    for text in ("❗️ КАБи", "Гучно!!!", "❗ Ще", "💯", "❤️ Запоріжжя", "❗️Пуски КАБів попередньо в бік Оріхова"):
        assert _monitoring_safety_exclusion(article(text)), text


def test_210_keep_official_meaningful_decisions():
    assert not _monitoring_safety_exclusion(article(
        "Розівська селищна військова адміністрація уклала меморандум щодо безоплатних юридичних консультацій для ВПО. Телефон 0958067950."
    ))
    assert not _monitoring_safety_exclusion(article(
        "11 жовтня у Запоріжжі оголошено День жалоби. Про це повідомила обласна військова адміністрація."
    ))


def test_210_block_service_text_at_publish_boundary():
    for text in ("**Готовий текст поста:** У Запоріжжі", "Джерело додасть footer.", "НЕ ПУБЛІКУВАТИ. Немає достатніх фактів."):
        assert _EDITORIAL_META_LEAK.search(text), text
