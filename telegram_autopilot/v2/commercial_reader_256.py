"""2.2.56: operator-approved mass-audience editorial criteria for commercial profile.

Applies by commercial editorial runtime profile, not channel name/source domain.
No source blacklist, invented hooks, extra AI calls, or budget/roster changes.
"""
from __future__ import annotations

from typing import Any, Mapping


COMMERCIAL_READER_RULE_256 = """
РЕДАКЦІЙНА ІДЕНТИЧНІСТЬ 2.2.56: «ПРОДАНО!» — не журнал товарного дизайну
і не вузькопрофесійний рекламний B2B-дайджест. Аудиторія — звичайна
допитлива людина, НЕ покупець цієї речі, НЕ дизайнер і НЕ маркетолог.
Головний тест: чи захоче вона показати або переказати цю історію другу?
Обов'язково відрізняй «предмет красивий/модульний/портативний»
від «сюжет має конкретний несподіваний поворот, мем, культурний контекст,
зрозумілу дивину, поведінку людей, вражаючий масштаб або несподіване
застосування». Фотографія без цікавої історії — недостатня підстава.

Позитивні ОРІЄНТИРИ оператора, а НЕ whitelist брендів:
плюшевий манул IKEA; Adidas × Pokémon; пошук загублених котів через ШІ;
спіральна скульптура MSCHF/Lexus; вірусна тінь дверей Aston Martin;
закулісся stop-motion Apple; мегаяхта з іншою яхтою та авто;
робот-гусак; резюме на торті; книжкові рейви;
Cup Noodles × Halloween; Snapchat × Harry Potter AR.
Важлива НЕ назва бренду, а конкретний сюжет, який хочеться переказати.

Негативні ОРІЄНТИРИ останньої стрічки, якщо немає ДОДАТКОВОЇ
доказової несподіванки у SOURCE: звичайна склянка; нова компактна сауна;
черговий крихітний будинок; дизайнерський скребок для 3D-принтера;
нова сумка з підсвічуванням; просто красивий павільйон;
специфікація чергового гаджета. Не відхиляй автоматично предметний
дизайн: наприклад, справді абсурдний предмет чи культурний кросовер
може мати сильний людський гачок.

Для кожної ПОЗИТИВНОЇ оцінки також поверни:
- story_class: viral_culture | brand_stunt | unexpected_use |
  human_behavior | surprising_research | remarkable_object |
  routine_object | trade_news | other.
- shareable_to_friend: true лише коли SOURCE дає справжній конкретний
  гачок, який має сенс для НЕфахівця без наміру купувати річ.
- share_hook_quote: короткий ДОСЛІВНИЙ уривок із SOURCE, що підтверджує
  цей гачок (порожньо, якщо доказу немає). Не вигадуй цитату.
- product_only: true, коли матеріал цікавий переважно як опис або
  специфікація товару/споруди, а не як самостійна історія.
Якщо product_only=true або story_class=routine_object/trade_news і
немає самостійного людського гачка, decision=reject, навіть якщо
новизна дизайну висока. Для суспільно цікавого контенту, культури,
незвичайних колаборацій, жартів, AI та реальної споживчої поведінки
оцінюй власний сюжет, а НЕ «наявність маркетингової механіки».
Не домислюй емоції, вірусність, популярність чи масштаби з одного фото.
""".strip()


_STORY_CLASSES = frozenset({
    "viral_culture", "brand_stunt", "unexpected_use", "human_behavior",
    "surprising_research", "remarkable_object", "routine_object",
    "trade_news", "other",
})


def normalized_reader_signal_256(value: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize optional AI metrics. Old responses stay compatible."""
    raw = str(value.get("story_class") or "").casefold().strip()
    return {
        "story_class": raw if raw in _STORY_CLASSES else "other",
        "shareable_to_friend": value.get("shareable_to_friend") is True,
        "product_only": value.get("product_only") is True,
        "share_hook_quote": str(value.get("share_hook_quote") or "").strip()[:180],
        "signal_present": any(k in value for k in
            ("story_class", "shareable_to_friend", "product_only")),
    }


def commercial_reader_veto_256(article: Any, value: Mapping[str, Any]) -> str:
    """High-confidence story-class veto, with source quote anti-hallucination.

    A general consumer story is never blocked merely for mentioning products,
    brands, sources, or domains. This is a positive-AI-response consistency
    check, not a source reputation ban or an automatic topic quota.
    """
    s = normalized_reader_signal_256(value)
    if not s["signal_present"]:
        return ""  # Legacy responses remain eligible under existing thresholds.
    catalog = s["product_only"] or s["story_class"] in ("routine_object", "trade_news")
    if not catalog:
        return ""
    if s["shareable_to_friend"]:
        # A verified concrete source phrase can demonstrate an exceptional
        # feature or cultural crossover even in an ordinary product category.
        try:
            source = str(article["raw_text"] or "")
        except (KeyError, TypeError, IndexError):
            source = str(getattr(article, "raw_text", "") or "")
        try:
            title = str(article["title"] or "")
        except (KeyError, TypeError, IndexError):
            title = str(getattr(article, "title", "") or "")
        quote = " ".join(s["share_hook_quote"].casefold().split())
        corpus = " ".join((title + " " + source).casefold().split())
        if len(quote) >= 14 and quote in corpus:
            return ""
    return "SOLD_CATALOG_ONLY_256: типова товарна/професійна новина без підтвердженого гачка для широкої аудиторії"
