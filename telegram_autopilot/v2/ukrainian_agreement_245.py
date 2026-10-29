"""Conservative Ukrainian post-translation agreement checks (2.2.45).

These detect *specific* mismatched relative-pronoun constructions in finished
Ukrainian copy. They never change facts, named entities, case or tense by
themselves. An AI writer/final editor is asked to repair from source and all
existing fact/safety checks run again. If still invalid, fail closed.
"""
from __future__ import annotations

import re

# Exact oblique feminine singular head nouns; nominative masc/neuter relative
# immediately after these forms is not a valid reference back to the head.
# We deliberately avoid a general suffix-only Russian/Ukrainian "grammar
# corrector" that could damage quotes, names and other antecedents.
_FEMININE_OBLIQUE = (
    "підозрою", "підозру", "технологією", "технологію",
    "системою", "систему", "компанією", "компанію",
    "організацією", "організацію", "програмою", "програму",
    "моделлю", "модель", "статтею", "статтю",
    "заявою", "заяву", "ініціативою", "ініціативу",
)
_BAD_RELATIVE = re.compile(
    r"(?iu)\b(" + "|".join(_FEMININE_OBLIQUE) +
    r")\s*,\s*(який|яке|котрий|котре)\b"
)

# 2.2.48: high-confidence mismatched adjacent subject/predicate forms.
# Never mechanically change endings, names or quotations.
_BAD_SUBJECT_VERB = (
    (
        re.compile(
            r"(?iu)\b(комети|молекули|речовини|дослідники|вчені|"
            r"джерела|системи|компанії|алгоритми|астероїди)\s+"
            r"(мав|мала|був|була|показав|показала|з'ясував|з'ясувала|"
            r"виявив|виявила|може)\b"
        ),
        "UK_SUBJECT_NUMBER: множина підмета і однина присудка",
    ),
    (
        re.compile(
            r"(?iu)\b(комета|молекула|речовина|система|компанія|програма|"
            r"публікація|новина|ракета|технологія|кислота)\s+"
            r"(мав|був|показав|виявив|зазначив|підтвердив|зберігся)\b"
        ),
        "UK_SUBJECT_GENDER: жіночий підмет і чоловічий присудок",
    ),
    (
        re.compile(
            r"(?iu)\b(дослідження|зіткнення|випробування|повідомлення|"
            r"рішення|джерело|питання)\s+"
            r"(мав|мала|був|була|показав|показала|"
            r"підтвердив|підтвердила|з'ясував|з'ясувала)\b"
        ),
        "UK_SUBJECT_GENDER: середній підмет і присудок іншого роду",
    ),
)

# Other directly attested live-production Ukrainian calques. Avoid broad
# heuristics here: an AI guard is no substitute for full morphology.
_BAD_PREPOSITION_CASE = (
    (re.compile(r"(?iu)\bзгідно\s+із?\s+звіт\b"),
     "UK_CASE: неправильний відмінок після «згідно з»"),
    # 2.2.51: real published 'нашої власної планетні системи':
    # genitive feminine head must not take nominative plural adjective.
    (re.compile(r"(?iu)\b(?:нашої|цієї|власної|такої)\s+(?:власної\s+)?планетні\s+системи\b"),
     "UK_CASE: «нашої/власної планетні системи» — потрібен родовий відмінок прикметника"),
)


def high_confidence_agreement_issues(text: str) -> tuple[str, ...]:
    """Zero-guess high-confidence veto for output immediately before Telegram."""
    value = str(text or "")
    issues: list[str] = []
    match = _BAD_RELATIVE.search(value)
    if match:
        issues.append(
            f"UK_RELATIVE_AGREEMENT: «{match.group(1)}, {match.group(2)}» "
            "не узгоджено в роді/числі. Перебудуй речення українською, "
            "не змінюючи твердження першоджерела."
        )
    for pattern, label in _BAD_PREPOSITION_CASE:
        if pattern.search(value):
            issues.append(label)
    for pattern, label in _BAD_SUBJECT_VERB:
        match = pattern.search(value)
        if match:
            issues.append(f"{label}: «{match.group(0)}». Перевір SOURCE і перебудуй речення.")
    return tuple(dict.fromkeys(issues))


POST_TRANSLATION_WRITER_RULE = """
ПІСЛЯ ПЕРЕКЛАДУ: перечитай увесь ГОТОВИЙ текст природною українською, а не
копіюй синтаксис SOURCE. Перевір рід, число й відмінок прикметників,
займенників, дієприкметників і підметів, особливо у підрядних реченнях
«який/яка/які» та після прийменників. Не допускай «за підозрою, який
висуває ШІ»: граматичний зв'язок має бути однозначним. Замість механічної
зміни одного закінчення можна перебудувати ТІЛЬКИ форму речення, зберігаючи
хто/що/кого/чому з SOURCE. Не додавати нових фактів, суб'єктів, причин,
не робити умовне твердження категоричним. Перевір граматику ОСТАННЬОЇ
версії перед відповіддю; не повертай чорновий переклад.
У 2.2.48 окремо перевір кожен підмет, присудок, відмінок і прийменник.
Якщо SOURCE говорить лише про моделювання, ймовірність або гіпотезу,
не перетворюй їх на доведений універсальний факт. Не вигадуй рейтингу
альтернативних пояснень, якщо SOURCE його не надає.
""".strip()

POST_TRANSLATION_FINAL_RULE = """
ОСТАННІЙ МОВНИЙ ПРОХІД ДЛЯ ВСІХ ТРЬОХ КАНАЛІВ.
1. Після фактчекінгу повторно перевір УЗГОДЖЕННЯ українського фінального
тексту: який/яка/яке/які, рід/відмінок іменників, прикметників,
числівників та дієслів; підмет і присудок.
2. Ніколи не залишай «підозрою, який», «системою, який», «програмою, яке».
Перебудуй саме речення, щоб читач точно розумів, хто виконує дію.
3. Зберігай імена, організації, дати, числа, цитати, контакти й правильну
силу тверджень. Не змінюй об'єктів та причинно-наслідкових зв'язків.
4. Якщо виправлення неоднозначне за SOURCE, не вигадуй факт: використовуй
простішу граматичну конструкцію, яка передає лише підтверджене.
ОСТАННЄ ЧИТАННЯ 2.2.48: відрізняй результат одного дослідження від
загального висновку; зберігай «може», «ймовірно», «за певних умов»;
перевір рід і число підмета й присудка, а також керування відмінків.
Не додавай жодних пояснень про власну перевірку.
""".strip()
