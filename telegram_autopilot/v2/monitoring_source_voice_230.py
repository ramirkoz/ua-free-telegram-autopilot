"""2.2.30: original-source voice and local-event context for monitoring news.

A local Telegram channel may forward a first-person political quotation or
react to somebody else's comment. That alone does not create a local civic
event, and an AI writer may not invent an anonymous "speaker" to compensate.
These narrowly scoped guards use immutable original text and do not rely on
the forwarding channel's title, model angle, or AI output as provenance.
"""
from __future__ import annotations

import re
from typing import Any


def _value(article: Any, field: str) -> str:
    try:
        value = article[field]
    except (KeyError, TypeError, IndexError):
        value = getattr(article, field, "")
    return str(value or "")


# The original body is authoritative for local relevance. A local-looking
# forwarding source name, Telegram URL or AI title is not local evidence.
_LOCAL_PLACE = re.compile(
    r"(?iu)\b(?:запоріж\w*|запоріз\w*|мелітопол\w*|бердянськ\w*|"
    r"енергодар\w*|токмак\w*|гуляйпол\w*|оріхів\w*|василів\w*|"
    r"полог\w*|приморськ\w*)\b"
)
_LOCAL_EFFECT = re.compile(
    r"(?iu)\b(?:мешканц\w*|жител\w*|громад\w*|постраждал\w*|"
    r"отрима\w*|відкри\w*|виплат\w*|евакуац\w*|"
    r"пошкодж\w*|запровад\w*|переда\w*|забезпеч\w*)\b"
)
_GLOBAL_POLICY = re.compile(
    r"(?iu)\b(?:тариф\w*|мит\w*|санкці\w*|торговельн\w*\s+війн\w*)\b"
)
_FOREIGN_POLICY_PARTIES = re.compile(
    r"(?iu)\b(?:росі\w*|російськ\w*|україн\w*|америк\w*|"
    r"сша|трамп\w*|путін\w*|trump|putin)\b"
)
_FIRST_PERSON_QUOTE = re.compile(
    r"(?iu)\b(?:я\s+(?:сказав|сказала|ніколи|думав|думала|заявив|"
    r"заявила|запропонував|запропонувала|вважаю|підкреслив|"
    r"підкреслила)|ми\s+(?:зупинили|припинили|домоглися|"
    r"сказали|запровадили))\b"
)
_MISSING_SPEAKER_IN_OUTPUT = re.compile(
    r"(?iu)\b(?:мовець|неназваний\s+(?:спікер|посадовець|"
    r"представник))\b|"
    r"\bу\s+заяв[іи]\s+(?:запропонували|заявили|зазначили)\b"
)


def original_global_commentary_reason(article: Any) -> str:
    """Block an unsupported national/global quotation as local news.

    Keep a genuine local policy impact or local resident consequence, and do
    not reject normal direct reports of a local event on word matches alone.
    """
    original = _value(article, "raw_text")[:8000]
    if not (_GLOBAL_POLICY.search(original)
            and _FOREIGN_POLICY_PARTIES.search(original)
            and _FIRST_PERSON_QUOTE.search(original)):
        return ""
    if _LOCAL_PLACE.search(original) and _LOCAL_EFFECT.search(original):
        return ""
    return "MONITORING_UNATTRIBUTED_GLOBAL_COMMENTARY_NOT_LOCAL"


def source_voice_output_reason(article: Any, final_text: str) -> str:
    """Catch a made-up anonymous narrator when the source quotes 'I/we'.

    The original political quotation may be attributed, but the generated
    report must not replace its identity with 'мовець' or anonymous 'they'.
    """
    original = _value(article, "raw_text")[:8000]
    if (_FIRST_PERSON_QUOTE.search(original)
            and _MISSING_SPEAKER_IN_OUTPUT.search(str(final_text or ""))):
        return "MONITORING_SOURCE_SPEAKER_LOST"
    return ""


SOURCE_VOICE_INSTRUCTION = (
    "\nАТРИБУЦІЯ Й ГОЛОС: відрізняй фактичну подію від цитати, "
    "думки автора каналу та його реакції на чужий допис. "
    "Якщо SOURCE цитує «я/ми», установи особу лише з підтвердженого "
    "першоджерела, не призначай автором цитати канал-переказувач. "
    "Не підміняй особу безіменним «мовець», «у заяві запропонували» "
    "чи схожим пасивним зворотом. Якщо особа і місцевий факт відсутні, "
    "не створюй із репліки самостійну новину. "
    "Поверни ЛИШЕ тіло публікації без «Текст поста:» та інших заголовків-інструкцій.\n"
)
