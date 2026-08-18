from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class QualityAssessment:
    score: int
    issues: tuple[str, ...]

    @property
    def needs_second_candidate(self) -> bool:
        return self.score < 86

    @property
    def publishable(self) -> bool:
        return self.score >= 78


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
