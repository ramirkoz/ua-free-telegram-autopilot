from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from .ukrainian_quality import language_quality_issues


@dataclass(frozen=True, slots=True)
class QualityAssessment:
    score: int
    issues: tuple[str, ...]

    @property
    def needs_second_candidate(self) -> bool:
        return self.score < 90

    @property
    def publishable(self) -> bool:
        return self.score >= 82


_AWKWARD_PHRASES = (
    "на столбі",
    "висота вартості",
    "висоту вартості",
    "слугував п'ять років",
    "слугував п’ять років",
    "дана технологія",
    "даний пристрій",
    "здійснює доставку",
    "здійснювати доставку",
    "має місце",
    "являється",
)

_WORD_RE = re.compile(r"[A-Za-zА-Яа-яІіЇїЄєҐґ0-9’'/-]+")


_RUSSIAN_ONLY_LETTERS_RE = re.compile(r"[ыэёъ]", re.I)
_ALPHA_SEGMENT_RE = re.compile(r"[A-Za-zА-Яа-яІіЇїЄєҐґЁёЫыЭэЪъ]{2,}")

_META_AUTHOR_RE = re.compile(
    r"(?:"
    r"\bавтор(?:а|у|ом|ові|і|ка|ки|ці|кою)?\s+(?:матеріалу|статті|огляду|публікації)\b|"
    r"\b(?:за\s+словами|на\s+думку)\s+автор(?:а|у|ом|ові|і|ка|ки|ці|кою)?\b|"
    r"\b(?:оглядач(?:а|у|ем|еві|і|ка|ки|ці|кою)?|редактор(?:а|у|ом|ові|і|ка|ки|ці|кою)?|журналіст(?:а|у|ом|ові|і|ка|ки|ці|кою)?)"
    r"\s+(?:видання|сайту|журналу|матеріалу|статті|огляду)\b"
    r")",
    re.I,
)

_HARD_STOPWORDS = {
    "але", "аби", "або", "без", "був", "була", "були", "було", "буде", "будуть", "від", "він", "вона",
    "вони", "воно", "для", "до", "його", "її", "їх", "із", "зі", "коли", "ми", "на", "над", "не", "ні",
    "після", "під", "по", "про", "та", "так", "також", "той", "того", "тому", "у", "в", "це", "цей", "ця",
    "ці", "що", "який", "яка", "яке", "які", "як", "чи", "ще", "вже", "може", "можуть", "має", "мають",
    "компанія", "компанії", "компанію", "система", "системи", "модель", "моделі", "матеріал", "матеріали",
    "новий", "нова", "нове", "нові", "року", "років", "під", "понад", "більш", "менш",
}
_HARD_SUFFIXES = (
    "уваннями", "юваннями", "ування", "ювання", "овувати", "атися", "итися", "увати", "ювати",
    "ними", "ного", "ному", "ями", "ами", "ові", "еві", "єві", "ого", "ому", "ими", "ій",
    "ою", "ею", "ів", "їв", "ах", "ях", "ий", "а", "я", "у", "ю", "і", "и", "е", "о",
)


def _hard_stem(token: str) -> str:
    value = token.casefold().replace("’", "'").strip("-'_/.")
    if len(value) < 5:
        return value
    if re.search(r"[а-яіїєґёыэъ]", value):
        for suffix in _HARD_SUFFIXES:
            if len(value) - len(suffix) >= 4 and value.endswith(suffix):
                return value[:-len(suffix)]
    return value


def hard_editorial_blockers(body: str) -> tuple[str, ...]:
    """High-confidence corruption signals that must never autopublish.

    These rules are intentionally structural rather than a dictionary of yesterday's
    typos.  They target the failure class seen in the RC29 overnight corpus: looping
    phrases, collapsed lexical variety, Russian-only letters, mixed alphabets inside
    one word and malformed unfinished quoting.  A normal imperfect sentence may still
    be sent to the trusted editor, but these patterns make the candidate unsafe as-is.
    """
    text = str(body or "").strip()
    if not text:
        return ("порожній текст",)
    clean = re.sub(r"https?://\S+", " ", text)
    issues: list[str] = []

    if _META_AUTHOR_RE.search(clean):
        issues.append("мета-коментар про автора/оглядача замість безособового викладу")

    segments = _ALPHA_SEGMENT_RE.findall(clean)
    if any(_RUSSIAN_ONLY_LETTERS_RE.search(segment) for segment in segments):
        issues.append("російські літери в українському тексті")
    if any(re.search(r"[A-Za-z]", segment) and re.search(r"[А-Яа-яІіЇїЄєҐґЁёЫыЭэЪъ]", segment) for segment in segments):
        issues.append("змішані латинські й кириличні літери всередині слова")

    words = [w.casefold().strip("’'-/") for w in _WORD_RE.findall(clean) if w.strip("’'-/")]
    for left, right in zip(words, words[1:]):
        # Repeated product/model identifiers can be legitimate in a compact list
        # (for example ``S26, S26+``). Treat only repeated Cyrillic lexical items
        # as a hard prose-corruption signal.
        if len(left) >= 3 and left == right and re.search(r"[а-яіїєґёыэъ]", left, re.I):
            issues.append("сусіднє слово повторено двічі")
            break

    sentences = [
        re.sub(r"\s+", " ", sentence.strip().casefold())
        for sentence in re.split(r"(?<=[.!?…])\s+", clean)
        if len(_WORD_RE.findall(sentence)) >= 4
    ]
    if sentences:
        sentence_counts = Counter(sentences)
        if max(sentence_counts.values(), default=0) >= 2:
            issues.append("ціле речення повторюється")

    # Repeated 4/5-word windows catch near-looping prose even when punctuation or
    # one inflection changes.  Thresholds are deliberately high to avoid punishing
    # legitimate references to the same product/company.
    if len(words) >= 8:
        four = Counter(tuple(words[i:i + 4]) for i in range(len(words) - 3))
        five = Counter(tuple(words[i:i + 5]) for i in range(len(words) - 4))
        if max(four.values(), default=0) >= 3 or max(five.values(), default=0) >= 2:
            issues.append("текст зациклюється на повторюваній фразі")

    content = [
        _hard_stem(word) for word in words
        if len(word) >= 3 and word not in _HARD_STOPWORDS and not word.isdigit()
    ]
    if len(content) >= 20:
        diversity = len(set(content)) / len(content)
        if diversity < 0.43:
            issues.append("аномально низька лексична різноманітність")
        counts = Counter(content)
        if counts:
            token, count = counts.most_common(1)[0]
            if count >= 6 and count / len(content) >= 0.17:
                issues.append(f"одна словоформа/основа неприродно домінує ({token})")

    # Plain ASCII quotes are common in scraped English source names. An odd count in
    # the final Ukrainian body usually means the generation stopped or mangled a quote.
    if clean.count('"') % 2:
        issues.append("незакрита лапка")

    return tuple(dict.fromkeys(issues))


def _sentences(value: str) -> list[str]:
    compact = " ".join(str(value or "").split())
    return [part.strip() for part in re.split(r"(?<=[.!?…])\s+", compact) if part.strip()]


def _paragraphs(value: str) -> list[str]:
    return [" ".join(part.split()).strip() for part in re.split(r"\n+", str(value or "")) if part.strip()]


def assess_rewrite(body: str, *, hard_limit: int) -> QualityAssessment:
    """Cheap deterministic quality gate used before optional extra AI work.

    The goal is not to judge literary taste. It catches the exact failure mode
    seen in live tests: technically valid Ukrainian that is dense, clause-heavy,
    literal or exhausting to read. A high score means the first candidate is
    good enough and no extra AI calls are needed.
    """
    text = str(body or "").strip()
    if not text:
        return QualityAssessment(0, ("порожній текст",))

    hard_blockers = hard_editorial_blockers(text)
    if hard_blockers:
        return QualityAssessment(20, hard_blockers)

    score = 100
    issues: list[str] = []
    sentences = _sentences(text)
    paragraphs = _paragraphs(text)
    word_counts = [len(_WORD_RE.findall(sentence)) for sentence in sentences]
    char_lengths = [len(sentence) for sentence in sentences]

    if len(text) >= 350 and len(paragraphs) < 2:
        score -= 25
        issues.append("суцільна стіна тексту")

    preferred_paragraph = 360 if hard_limit <= 900 else 620
    longest_paragraph = max((len(p) for p in paragraphs), default=0)
    if longest_paragraph > preferred_paragraph:
        score -= 14
        issues.append("надто довгий абзац")

    max_words = max(word_counts, default=0)
    avg_words = (sum(word_counts) / len(word_counts)) if word_counts else 0.0
    if max_words > 28:
        score -= 18
        issues.append("є перевантажене речення понад 28 слів")
    elif max_words > 24:
        score -= 8
        issues.append("є задовге речення")
    if avg_words > 21:
        score -= 13
        issues.append("зависока середня довжина речення")
    elif avg_words > 18.5:
        score -= 5
        issues.append("речення можна зробити коротшими")

    if max(char_lengths, default=0) > 240:
        score -= 12
        issues.append("одне речення надто довге за структурою")

    semicolon_count = text.count(";")
    colon_count = text.count(":")
    if semicolon_count >= 2:
        score -= min(10, 3 * semicolon_count)
        issues.append("забагато складених конструкцій через крапку з комою")
    if colon_count >= 3 and len(sentences) <= 6:
        score -= 5
        issues.append("забагато переліків у реченнях")

    low = text.casefold()
    awkward = [phrase for phrase in _AWKWARD_PHRASES if phrase in low]
    if awkward:
        score -= min(24, 10 + 5 * (len(awkward) - 1))
        issues.append("неприродна або калькована українська")

    language_issues = language_quality_issues(text)
    if language_issues:
        penalty = min(24, 8 + 4 * (len(language_issues) - 1))
        severe = sum(1 for issue in language_issues if any(mark in issue for mark in ("оціночне", "реклам", "безапеляційне")))
        penalty += min(12, 8 * severe)
        score -= penalty
        issues.extend(language_issues[:4])

    # Repeated sentence starts make short Telegram posts sound mechanical.
    starts: list[str] = []
    for sentence in sentences:
        words = [w.casefold() for w in _WORD_RE.findall(sentence)[:2]]
        if words:
            starts.append(" ".join(words))
    repeated = max((starts.count(item) for item in set(starts)), default=0)
    if repeated >= 3:
        score -= 7
        issues.append("повторюються однакові початки речень")

    if hard_limit <= 900 and len(text) > 860:
        score -= 4
        issues.append("текст занадто щільно притиснутий до ліміту")

    return QualityAssessment(max(0, min(100, score)), tuple(dict.fromkeys(issues)))


def build_revision_feedback(assessment: QualityAssessment) -> str:
    if not assessment.issues:
        return "Make the rewrite more natural, concise and easy to read without changing facts."
    return "Fix these readability problems: " + "; ".join(assessment.issues[:5]) + "."
