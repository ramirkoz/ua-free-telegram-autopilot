"""2.2.54: source-bounded, channel-role-aware editorial tone hints.

Presentation guidance only: no additional AI calls or rejection gates,
no inference of casualties, military status, intent, material or outcomes.
All classification is from the exact article's source title/raw text.
"""
from __future__ import annotations

import re
from typing import Any


_MEMORIAL = re.compile(
    r"(?iu)\b(?:прощанн\w*|попрощал\w*|попрощалися|"
    r"поховал\w*|похованн\w*|вшанувал\w*\s+пам['’]ять|"
    r"farewell\s+ceremony|funeral\s+for)\b"
)
_SERVICE_MEMBER = re.compile(
    r"(?iu)\b(?:захисник\w*|захисниц\w*|військовослужбов\w*|"
    r"сапер\w*|нацгварді\w*|гвардієц\w*|"
    r"military\s+engineer|serviceman|soldier|sapper)\b"
)
_DEATH = re.compile(
    r"(?iu)\b(?:загинув|загинула|загибли\w*|полегл\w*|помер\w*|"
    r"killed|died|fallen)\b"
)
_DESIGN_OBJECT = re.compile(
    r"(?iu)\b(?:павільйон\w*|альтанк\w*|лавк\w*|"
    r"переносн\w*\s+(?:споруд\w*|павільйон\w*)|"
    r"pavilion\w*|gazebo|furniture|bench|shelter)\b"
)
_DESIGN_MECHANISM = re.compile(
    r"(?iu)\b(?:розклада\w*|склада\w*|трансформу\w*|перенос\w*|"
    r"складен\w*|перероблен\w*|розібран\w*|reuse\w*|"
    r"fold\w*|transform\w*|portable|recycl\w*|repurpos\w*)\b"
)

_MEMORIAL_RULE = (
    "ТОН 2.2.54 | ПРОЩАННЯ З ВІЙСЬКОВИМ: стриманий, людяний і поважний. "
    "Спочатку ім'я, підтверджений статус та що сталося; далі дата, "
    "обставини і місце прощання ЛИШЕ з SOURCE. "
    "Після імені краще «він служив» або «військовослужбовець служив», "
    "аніж знеособлене «чоловік служив». "
    "Не додавати вигаданих подвигів, родичів, цитат, епітетів, героїчної "
    "риторики або закликів. Не міняти час смерті на час поранення."
)
_DESIGN_RULE = (
    "ТОН 2.2.54 | ДИЗАЙН / ТРАНСФОРМАЦІЯ: перший абзац одразу пояснює "
    "неочікуваний принцип: що саме змінюється та як працює предмет, "
    "з точним ім'ям студії/об'єкта. Не починай лише із сухого "
    "«студія створила X», якщо SOURCE підтверджує конкретну цікаву механіку. "
    "Використані матеріали і тонкі технічні подробиці винеси в другий "
    "короткий абзац. Поясни практичну користь лише коли її назвав SOURCE. "
    "Не вигадуй екологічного ефекту, суспільної місії чи задуму авторів."
)
_SCIENCE_RULE = (
    "ТОН 2.2.54 | НАУКА: почни з головного спостереження, відділи "
    "спостережуваний результат від можливого пояснення. "
    "Стандартне формулювання: «дослідження виявило зв'язок, "
    "але не доводить причинно-наслідкового зв'язку» (ЛИШЕ якщо "
    "SOURCE справді обмежує висновок кореляцією). "
    "Перевага коротких двох абзаців над довгим переліком термінів; "
    "не посилюй «у великих масштабах» до «у промислових обсягах» "
    "без явного джерела. Зберігай точні числа і межі дослідження."
)
_GENERAL_RULE = (
    "ТОН 2.2.54: перше речення містить головний підтверджений факт, "
    "далі лише необхідний механізм/контекст. Кожен абзац має нову "
    "інформацію; не подвоюй ту саму думку й не вигадуй наслідків "
    "для «сильнішого» фіналу."
)


def _read(article: Any, key: str) -> str:
    try:
        val = article[key]
    except (KeyError, IndexError, TypeError):
        val = getattr(article, key, "")
    return str(val or "")


def editorial_tone_kind(
    article: Any, *, monitoring: bool = False,
    commercial: bool = False, science: bool = False,
) -> str:
    """Resolve one source-based editorial style, never by channel ID/name."""
    source = (_read(article, "title") + "\n" + _read(article, "raw_text"))[:12000]
    if monitoring and _MEMORIAL.search(source) and _SERVICE_MEMBER.search(source) and _DEATH.search(source):
        return "memorial"
    if commercial and _DESIGN_OBJECT.search(source) and _DESIGN_MECHANISM.search(source):
        return "design_transform"
    if science:
        return "science"
    return "general"


def editorial_tone_rules(
    article: Any, *, monitoring: bool = False,
    commercial: bool = False, science: bool = False, final: bool = False,
) -> str:
    kind = editorial_tone_kind(
        article, monitoring=monitoring, commercial=commercial, science=science
    )
    text = {
        "memorial": _MEMORIAL_RULE,
        "design_transform": _DESIGN_RULE,
        "science": _SCIENCE_RULE,
        "general": _GENERAL_RULE,
    }[kind]
    if final:
        text += (
            " ФІНАЛЬНА ПЕРЕВІРКА: не змінюй дат, учасників, чисел, "
            "модальності чи причини події заради стилю. "
            "Якщо чернетка вже точна й читабельна, залиш її без змін."
        )
    return text
