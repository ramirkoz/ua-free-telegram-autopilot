from types import SimpleNamespace

from telegram_autopilot.v2.editorial import _monitoring_official_context_reject


def item(raw_text: str, source_name: str = "ЗАПОРІЖЖЯ.INFO"):
    return SimpleNamespace(raw_text=raw_text, title=raw_text, source_name=source_name)


def test_live_operator_four_bad_cases():
    assert _monitoring_official_context_reject(item("⁉️Чий малий бігає в районі Comfort city?")) == "MONITORING_PRIVATE_ANNOUNCEMENT"
    assert _monitoring_official_context_reject(item(
        "У районі Лахті тимчасово зникло світло. Підписники повідомили про відключення, але електрику вже відновили."
    ))
    assert _monitoring_official_context_reject(item(
        "❗️Чиї ключі? Т. 066 8811407\n\nЗагубили у маршрутці 63А вейп. Якщо хтось знайде, поверніть за винагороду 0759355986"
    ))
    assert _monitoring_official_context_reject(item(
        "У парку Міст-побратимів люди напилися, чіпляються до підлітків. Про це пишуть читачі."
    )) == "MONITORING_READER_RUMOR_NOT_OFFICIAL"


def test_official_material_remains_eligible():
    assert not _monitoring_official_context_reject(item(
        "Комишуваська селищна військова адміністрація повідомила про зміну місця прийому громадян через безпекову ситуацію.",
        "Комишуваська громада",
    ))
    assert not _monitoring_official_context_reject(item(
        "Департамент соціального захисту Запорізької міської ради оголосив прийом заявок на допомогу ВПО.",
        "Запорізька міська рада",
    ))


def test_news_aggregator_without_official_source_is_rejected():
    assert _monitoring_official_context_reject(item(
        "У місті оголошено новий графік роботи пунктів підтримки", "ЗАПОРІЖЖЯ.INFO"
    )) == "MONITORING_SOURCE_NOT_OFFICIAL"
    assert _monitoring_official_context_reject(item(
        "У районі тимчасово відсутнє світло, відновлення триває", "ЗаБор Запоріжжя"
    ))
