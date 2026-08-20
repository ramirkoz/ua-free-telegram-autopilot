from __future__ import annotations

import re

# Conservative, deterministic fixes for mistakes actually observed in live
# autopilot posts.  They only repair spelling/standard Ukrainian wording and do
# not add facts, names, numbers, attribution or new conclusions.
_SAFE_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bнеочіківан", re.I), "несподіван"),
    (re.compile(r"\bчехол\b", re.I), "чохол"),
    (re.compile(r"\bчехла\b", re.I), "чохла"),
    (re.compile(r"\bчехлу\b", re.I), "чохлу"),
    (re.compile(r"\bчехлом\b", re.I), "чохлом"),
    (re.compile(r"\bчехлі\b", re.I), "чохлі"),
    (re.compile(r"\bчехли\b", re.I), "чохли"),
    (re.compile(r"\bчехлів\b", re.I), "чохлів"),
    (re.compile(r"\bчехлами\b", re.I), "чохлами"),
    (re.compile(r"\bКікстенд\b"), "Підставка"),
    (re.compile(r"\bкікстенд\b"), "підставка"),
    (re.compile(r"\bскачк", re.I), "стрибк"),
    (re.compile(r"\bрозплавеного\s+солі\b", re.I), "розплавленої солі"),
    (re.compile(r"\bрозплавена\s+сіль\b", re.I), "розплавлена сіль"),
    (re.compile(r"\bрозплавеною\s+сіллю\b", re.I), "розплавленою сіллю"),
    (re.compile(r"\bзадоволення\s+стрибк", re.I), "покриття стрибк"),
    (re.compile(r"\bпри\s+несподіваному\s+русі\b", re.I), "під час несподіваного руху"),
    (re.compile(r"\bверсія\s+була\s+сировиною\b", re.I), "версія була сирою"),
    (re.compile(r"\bперша\s+версія\s+була\s+сировиною\b", re.I), "перша версія була сирою"),
    (re.compile(r"\bна\s+даний\s+момент\b", re.I), "зараз"),
    (re.compile(r"\bприймати\s+участь\b", re.I), "брати участь"),
    (re.compile(r"\bприйняти\s+участь\b", re.I), "взяти участь"),
    (re.compile(r"\bпо\s+даним\b", re.I), "за даними"),
    (re.compile(r"\bAndroid\s+флагман", re.I), "Android-флагман"),
    (re.compile(r"\bне\s+дивлячись\s+на\b", re.I), "попри"),
    (re.compile(r"\bслідуюч(ий|а|е|і|ого|ому|ою|ими)\b", re.I), r"наступн\1"),
    # Live-corpus fixes. These are narrow lexical/grammar repairs and do
    # not create facts or alter named entities/numbers.
    (re.compile(r"\bРанніше\b"), "Раніше"),
    (re.compile(r"\bранніше\b", re.I), "раніше"),
    (re.compile(r"\bдругое\b", re.I), "друге"),
    (re.compile(r"\bкористувачської\b", re.I), "користувацької"),
    (re.compile(r"\bменталіжн(ість|ості|істю)\b", re.I), r"ментальн\1"),
    (re.compile(r"\bне\s+на\s+продажі\b", re.I), "не продається"),
    (re.compile(r"\bжит[ёе]л\b", re.I), "місць проживання"),
    (re.compile(r"\bвід['’]?ємн(ими|і|ий|ого)\s+пропелер", re.I), r"знімн\1 пропелер"),
    (re.compile(r"\bметодом\s+зворотного\s+інженерії\b", re.I), "методом зворотної інженерії"),
    (re.compile(r"\bножках\b", re.I), "ніжках"),
    (re.compile(r"\bплательник(и|ів|ам|ами)?\b", re.I), r"платник\1"),
    (re.compile(r"\bрівень\s+власної\s+виробництва\b", re.I), "рівень власного виробництва"),
    (re.compile(r"\bползунк(ом|а|у|и|ів)?\b", re.I), r"повзунк\1"),
    (re.compile(r"\bнову\s+плану\b", re.I), "новий план"),
    (re.compile(r"\bбез\s+річності\s+контрактів\b", re.I), "без річних контрактів"),
    (re.compile(r"\bпонад\s+у\s+(\d+)\s+країн", re.I), r"у понад \1 країн"),
    (re.compile(r"\bпрактично\s+в\s+монополію\b", re.I), "майже монопольно"),
    (re.compile(r"\bу\s+першому\s+півроці\b", re.I), "у першому півріччі"),
    (re.compile(r"\bзростаюч(?:і|ої|у)\s+геополітичн(?:і|ої|у)\s+напруг(?:и|а|у)\b", re.I), "зростання геополітичної напруги"),
    (re.compile(r"\bодним\s+з\s+малого\s+числа\b", re.I), "одним із небагатьох"),
    (re.compile(r"\bу\s+спільному\s+наради\b", re.I), "у спільному повідомленні"),
    (re.compile(r"\bголовний\s+небезпечний\s+пастка\b", re.I), "головна небезпечна пастка"),
    (re.compile(r"\bв\s+відповідь\b", re.I), "у відповідь"),
    (re.compile(r"\bв\s+Китаї\b"), "у Китаї"),
    (re.compile(r"\bв\s+Індії\b"), "в Індії"),
    (re.compile(r"\bжгут\b", re.I), "джгут"),
    (re.compile(r"\bближче\s+інфрачервон", re.I), "ближнє інфрачервон"),
    (re.compile(r"\bнайясніш(ий|а|е|і|ого|ому|ою|ими)\b", re.I), r"найочевидніш\1"),
    (re.compile(r"\bхакері\b", re.I), "хакери"),
    (re.compile(r"\bсертифікуюч(а|ої|у|ою)\s+організаці", re.I), r"сертифікаційн\1 організаці"),
    (re.compile(r"\bпроект(?!or)(у|ом|і|ах|ами|ів|и)?\b", re.I), r"проєкт\1"),
    (re.compile(r"\bпонад\s+у\s+три\s+рази\b", re.I), "більш ніж утричі"),
    # Gross agreement/calque errors observed in live posts.
    (re.compile(r"\bПодібний\s+тепловий\s+мап\b"), "Подібна теплова карта"),
    (re.compile(r"\bподібний\s+тепловий\s+мап\b", re.I), "подібна теплова карта"),
    (re.compile(r"\bТепловий\s+мап\b"), "Теплова карта"),
    (re.compile(r"\bтепловий\s+мап\b", re.I), "теплова карта"),
    (re.compile(r"\bГучний\s+гудіння\b"), "Гучне гудіння"),
    (re.compile(r"\bгучний\s+гудіння\b", re.I), "гучне гудіння"),
    (re.compile(r"\bНад\s+водой\b"), "Над водою"),
    (re.compile(r"\bнад\s+водой\b", re.I), "над водою"),
    (re.compile(r"\bПрямий\s+у\s+басейн\b"), "Прямо у басейн"),
    (re.compile(r"\bпрямий\s+у\s+басейн\b", re.I), "прямо у басейн"),
    (re.compile(r"\bТерміни\s+релізу\s+немає\b"), "Терміни релізу невідомі"),
    (re.compile(r"\bтерміни\s+релізу\s+немає\b", re.I), "терміни релізу невідомі"),
    (re.compile(r"\bВідео\s+з\s+моменту\b"), "Відео цього моменту"),
    (re.compile(r"\bвідео\s+з\s+моменту\b", re.I), "відео цього моменту"),
    (re.compile(r"\bсаме\s+в\s+тиждень,\s+коли\b", re.I), "саме того тижня, коли"),
    (re.compile(r"\bвиглядає\s+сировим\b", re.I), "виглядає сирим"),
    (re.compile(r"\bзгоріть\b", re.I), "згорить"),
    (re.compile(r"\bмісія\s+рятування\s+спостерігача\s+Swift\b", re.I), "місія порятунку обсерваторії Swift"),
    (re.compile(r"\bмісію\s+рятування\s+спостерігача\s+Swift\b", re.I), "місію порятунку обсерваторії Swift"),
)

# These are not blindly replaced because the right wording depends on context.
# They trigger an optional copy-edit pass and lower the quality score, but never
# by themselves send a factually safe story to retry.
_LANGUAGE_RISK_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bодн(?:а|ією|им|ого|ій)\s+з\s+найкращ", re.I), "неатрибутоване оціночне твердження «один з найкращих»"),
    (re.compile(r"\bеталонн\w*\s+рішенн", re.I), "канцелярсько-рекламна конструкція «еталонне рішення»"),
    (re.compile(r"\bідеально\s+підход", re.I), "безапеляційне «ідеально підходить»"),
    (re.compile(r"\bза\s+лічильником\b", re.I), "буквальна калька «за лічильником»"),
    (re.compile(r"\bдата-центров(?:ий|ого|ому|им|і|их)\b", re.I), "важка калькована конструкція «дата-центровий»"),
    (re.compile(r"\bздійсню(?:є|вати|ють)\s+(?:доставк|підтримк|робот)", re.I), "канцелярська конструкція зі «здійснювати»"),
    (re.compile(r"\bкікстенд\b", re.I), "неприродний загальний англіцизм «кікстенд»"),
    (re.compile(r"\bу\s+самого\s+аксесуара\b", re.I), "калькована конструкція «у самого аксесуара»"),
    (re.compile(r"\bвідчуття\s+наблизил(?:ося|ись)\b", re.I), "неприродна абстрактна калька про «відчуття»"),
    (re.compile(r"\bявляється\b", re.I), "русизм «являється»"),
)


_EDITORIAL_SENTENCE_PATTERNS = (
    re.compile(r"\bодн(?:а|ією|им|ого|ій)\s+з\s+найкращ", re.I),
    re.compile(r"\bідеально\s+підход", re.I),
    re.compile(r"\bеталонн\w*\s+рішенн", re.I),
)
_ATTRIBUTION_MARKERS = (
    "автор", "авторка", "оглядач", "журналіст", "на думку", "за словами",
    "видання вважає", "компанія вважає", "дослідники вважають", "називає це",
)

def remove_unattributed_editorial_sentences(value: str) -> str:
    """Drop nonessential hype/opinion sentences when they are presented as facts.

    Deletion is intentionally safer than inventing an attribution or rewriting
    the claim. Sentences that explicitly attribute an opinion are preserved for
    the optional copy-edit pass. Paragraph structure is retained.
    """
    text = str(value or "").strip()
    if not text:
        return text
    out_paragraphs: list[str] = []
    for paragraph in re.split(r"\n+", text):
        compact = " ".join(paragraph.split()).strip()
        if not compact:
            continue
        sentences = [part.strip() for part in re.split(r"(?<=[.!?…])\s+", compact) if part.strip()]
        kept: list[str] = []
        for sentence in sentences:
            low = sentence.casefold()
            editorial = any(pattern.search(sentence) for pattern in _EDITORIAL_SENTENCE_PATTERNS)
            attributed = any(marker in low for marker in _ATTRIBUTION_MARKERS)
            if editorial and not attributed:
                continue
            kept.append(sentence)
        if kept:
            out_paragraphs.append(" ".join(kept))
    return "\n\n".join(out_paragraphs).strip()

def apply_safe_ukrainian_fixes(value: str) -> str:
    text = str(value or "")
    for pattern, replacement in _SAFE_REPLACEMENTS:
        text = pattern.sub(replacement, text)
    # Keep formatting stable while cleaning accidental doubled spaces caused by
    # replacements. Paragraph breaks are preserved.
    text = "\n".join(re.sub(r"[ \t]{2,}", " ", line).strip() for line in text.splitlines())
    return text.strip()


def language_quality_issues(value: str) -> tuple[str, ...]:
    text = str(value or "")
    issues: list[str] = []
    # If a deterministic fixer would change the text, the original contains a
    # known live-production language problem.
    if apply_safe_ukrainian_fixes(text) != text.strip():
        issues.append("відомий русизм, калька або орфографічна помилка")
    for pattern, label in _LANGUAGE_RISK_PATTERNS:
        if pattern.search(text):
            issues.append(label)
    return tuple(dict.fromkeys(issues))


_HARD_LANGUAGE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bгучний\s+гудіння\b", re.I), "порушене узгодження «гучний гудіння»"),
    (re.compile(r"\bтепловий\s+мап\b", re.I), "порушене узгодження «тепловий мап»"),
    (re.compile(r"\bподібний\s+теплова\s+карта\b", re.I), "порушене узгодження після виправлення heat map"),
    (re.compile(r"\bнад\s+водой\b", re.I), "русизм/неправильний відмінок «над водой»"),
    (re.compile(r"\bпрямий\s+у\s+басейн\b", re.I), "неправильна форма «прямий у басейн»"),
    (re.compile(r"\bтерміни\s+релізу\s+немає\b", re.I), "порушене узгодження «терміни релізу немає»"),
    (re.compile(r"\bвиглядає\s+сировим\b", re.I), "калькована форма «виглядає сировим»"),
    (re.compile(r"\bзгоріть\b", re.I), "наказова форма «згоріть» замість майбутнього часу «згорить»"),
    (re.compile(r"\bчех(ол|ла|ли|лів|лом|лу|лі)\b", re.I), "русизм «чехол/чехли»"),
    (re.compile(r"\bползунк", re.I), "русизм «ползунок»"),
    (re.compile(r"\bплательник", re.I), "русизм «плательник»"),
    (re.compile(r"\bнеочіківан", re.I), "ненормативна форма «неочіківан…»"),
)


def final_language_blockers(value: str) -> tuple[str, ...]:
    """High-confidence language failures that must never autopublish."""
    text = str(value or "")
    return tuple(dict.fromkeys(label for pattern, label in _HARD_LANGUAGE_PATTERNS if pattern.search(text)))


_HUMAN_STYLE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bце\s+дозволяє\b", re.I), "шаблонне «це дозволяє»"),
    (re.compile(r"\bголовна\s+перевага\b", re.I), "шаблонна конструкція «головна перевага»"),
    (re.compile(r"\bце\s+поєднує\b", re.I), "шаблонний підсумок «це поєднує»"),
    (re.compile(r"\bу\s+результаті\b", re.I), "шаблонний підсумок «у результаті»"),
    (re.compile(r"\bварто\s+зазначити\b", re.I), "канцелярське «варто зазначити»"),
    (re.compile(r"\bслід\s+зазначити\b", re.I), "канцелярське «слід зазначити»"),
    (re.compile(r"\bна\s+ринку\b", re.I), "шаблонний ринковий вступ"),
)


def human_style_issues(value: str) -> tuple[str, ...]:
    text = str(value or "")
    issues: list[str] = []
    for pattern, label in _HUMAN_STYLE_PATTERNS:
        if pattern.search(text):
            issues.append(label)
    paragraphs = [p.strip() for p in re.split(r"\n+", text) if p.strip()]
    sentences = [p for p in re.split(r"(?<=[.!?…])\s+", " ".join(paragraphs)) if p.strip()]
    if len(text) > 1800 and len(paragraphs) >= 5:
        issues.append("надмірно довгий переказ джерела")
    if len(sentences) >= 7:
        starters = [re.sub(r"[^А-Яа-яІіЇїЄєҐґA-Za-z]+", "", s.split()[0]).casefold() for s in sentences if s.split()]
        if starters and max(starters.count(x) for x in set(starters)) >= 3:
            issues.append("монотонний ритм речень")
    return tuple(dict.fromkeys(issues))


def needs_human_copyedit(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if language_quality_issues(text) or human_style_issues(text):
        return True
    paragraphs = [p.strip() for p in re.split(r"\n+", text) if p.strip()]
    return len(text) >= 1200 or len(paragraphs) >= 5


def has_language_quality_risk(value: str) -> bool:
    return bool(language_quality_issues(value))
