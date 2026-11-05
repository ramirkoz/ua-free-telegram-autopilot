"""2.3.12: topic preferences from a *completed* operator review, 05 Nov 2026.

The 319 returned decisions are fully binary: only ☑ is positive; blank, —,
and ☐ are negative. This is editorial *preference*, never authorization to
relax freshness, full-source sufficiency, factuality, deduplication, media
provenance, or delivery safety. Examples are decision boundaries, not
publisher, brand, article-ID, or URL whitelists.
"""
from __future__ import annotations

from typing import Any
import re
from urllib.parse import urlsplit


SCIENCE = (
    "РЕДАКТОРСЬКА КАЛІБРАЦІЯ 2.3.12, CTRL+UA: у завершеній добірці "
    "120 із 230 тем відібрано, 110 відхилено. "
    "ВІДБИРАЙ конкретні наукові й технологічні результати, дієві кіберзагрози, "
    "нові методи дослідження, цікаві факти про мозок, медицину, космос, "
    "енергетику, робототехніку, нові цифрові можливості та їхній реальний "
    "вплив на людей. Не вимагай від цікавої технології революційності; "
    "вагомим може бути зрозумілий науковий результат або конкретна зміна платформи. "
    "РЕДАКТОР ВІДХИЛИВ: спекулятивну колонку про ймовірну майбутню пандемію "
    "без нового підтвердженого результату; вузький хобійний проєкт гітарних "
    "педалей без широкої інженерної новизни; знижки, купівельні добірки, "
    "звичайні огляди гаджетів, чисті виборчі суперечки та корпоративний PR. "
    "Так само не підміняй технологічну новину прогнозом аналітиків про "
    "майбутні потужності корпоративних дата-центрів без нового перевіреного "
    "наукового, інженерного чи суспільно значущого результату. "
    "Маркери «ШІ», «смарт», «технологія», бренд чи престиж видання самі "
    "по собі НЕ роблять матеріал цікавою новиною. "
    "Відрізняй перевірене дослідження від тривожної думки; просту "
    "майстерню від нового принципу. Дійсна нова кіберзагроза чи приклад "
    "значущого використання технології можуть бути профільними навіть "
    "без нової фізичної розробки. Не забороняй усі думки або любительські "
    "проєкти автоматично: оцінюй наявність конкретного предметного результату. "
    "Не підвищуй fit без повного джерельного підтвердження."
)

CREATIVE = (
    "РЕДАКТОРСЬКА КАЛІБРАЦІЯ 2.3.12, ПРОДАНО!: у завершеній добірці "
    "39 із 89 тем відібрано, 50 відхилено. "
    "ВІДБИРАЙ незвичайний фізичний предмет або механізм, справжній "
    "дизайнерський експеримент, цікаву форму чи ідею, виразну рекламну "
    "кампанію з конкретним творчим прийомом, попкультурну колаборацію "
    "з поясненою механікою, неочікуваний брендовий сюжет. "
    "Редактор обрав креативні рекламні історії з Dogs Trust, "
    "Deutsche Telekom, KFC × Doctor Doom і плакатну ідею British Airways: "
    "кампанії НЕ повинні мати нового товару, технології чи ROI, "
    "коли їхня художня ідея справді оригінальна. "
    "Редактор відкинув просте перефарбування футбольної форми, "
    "звичайний текстовий логотип пекарні, портфоліо агенції з "
    "переліком клієнтів, типову складну зарядну підставку без нового "
    "принципу та розпродаж настільної консолі. "
    "Не приймай будь-яку нову айдентику лише через слово «дизайн»: "
    "має бути конкретний незвичайний візуальний прийом, процес або сенс. "
    "Не відкидай креативну соціальну рекламу як «рутинний PR», "
    "поки не прочитав конкретну механіку її сюжету. "
    "Розмежовуй новий продукт та незалежний концепт; безпідставні "
    "анонси, кадрові/галузеві пресрелізи, цінові акції, "
    "каталожні переліки та звичайні стилізації без нової ідеї відхиляй. "
    "Відбір не є списком дозволених брендів або видавців; "
    "факти лише з перевіреного першоджерела."
)


def calibrated_feedback_2312(role: str) -> str:
    return SCIENCE if role == "science" else CREATIVE if role == "creative" else ""


def source_only_promotion_veto_2312(role: str, article: Any) -> str:
    """Conservative editorial veto: explicitly priced promotion/deals page.

    A price mentioned in a *substantive* new product article is not enough;
    a verified design experiment may still be interesting. This veto is for
    articles explicitly framed as retailer discount announcements.
    """
    if role not in {"science", "creative"}:
        return ""
    def field(name: str) -> str:
        try:
            value = article[name]
        except (KeyError, TypeError, IndexError):
            value = getattr(article, name, "")
        return str(value or "")
    url = field("source_url") or field("canonical_source_url")
    path = urlsplit(url).path.casefold()
    if "/deals/" not in path:
        return ""
    title = field("title").casefold()
    if re.search(
        r"(?iu)\b(?:discount\w*|cheaper|savings?|deals?|sales?|"
        r"знижк\w*|дешевш\w*|розпродаж\w*|заощад\w*)\b|"
        r"\bsave\s*[$€£]?\d+", title,
    ):
        return "EDITORIAL_OPERATOR_PRICE_PROMO_2312"
    return ""
