"""2.3.47: source-grounded result completeness for long research articles.

A source describing a controlled study must not become an empty methods-only
Telegram post. This supplements, rather than replaces, fact/claim validation.
No new AI call, no source retrieval, no inferred conclusions. Fail closed only
when the evidence and methods-only presentation are both highly explicit.
"""
from __future__ import annotations

import re
from typing import Any

_TITLE_RESEARCH = re.compile(
    r"(?iu)\b(?:research|scientific|scientist|study|studies|psychology|"
    r"neuroscience|experiment|clinical|trial|дослідженн\w*|науков\w*|"
    r"експеримент\w*|психолог\w*|вчен\w*)\b"
)
_SOURCE_METHOD = re.compile(
    r"(?i)\b(?:participants|students|subjects|experiment|control group|"
    r"randomly assigned|randomized trial)\b"
)
_SOURCE_FINDING = re.compile(
    r"(?i)\b(?:found(?:\s+no)?|reported\s+(?:higher|lower)|"
    r"showed|revealed|indicated|increased|decreased|"
    r"significant differences|not statistically significant|"
    r"no (?:evidence|effect|difference)|provided evidence favoring)\b"
)
_SENTENCE_BREAK = re.compile(r"(?<=[.!?…])\s+(?=[A-ZА-ЯІЇЄҐ“«])")
_METHODS_UA = re.compile(
    r"(?iu)\b(?:експеримент\w*|дослід\w*|студент\w*|"
    r"учасник\w*|лаборатор\w*|рандомізован\w*)\b"
)
_DIRECTION_UA = re.compile(
    r"(?iu)\b(?:виявил\w*|виявлял\w*|знайшл\w*|довел\w*|"
    r"показал\w*|засвідчил\w*|встановил\w*|"
    r"зросл\w*|зростал\w*|підвищил\w*|посилил\w*|"
    r"знизил\w*|зменшил\w*|послабил\w*|послаблювал\w*|"
    r"відрізнял\w*|змінювал\w*|змінил\w*|"
    r"помітніш\w*|вищ\w*|нижч\w*|частіш\w*|рідш\w*|"
    r"впливал\w*|не\s+вплинул\w*)\b"
)
_MEASURE_UA = re.compile(
    r"(?iu)\b(?:агресі\w*|емпаті\w*|гнів\w*|злост\w*|"
    r"ставленн\w*|поведінк\w*|тривож\w*|страх\w*|"
    r"відмінност\w*|різниц\w*|показник\w*|оцінк\w*|"
    r"рівн\w*|частот\w*|ризик\w*|пам.?ят\w*|"
    r"запам.?ят\w*|уваг\w*|відчутт\w*|"
    r"гачк\w*|мелоді\w*|фраз\w*|слухач\w*|"
    r"реакці\w*|самопочутт\w*|симптом\w*|"
    r"продуктивн\w*|статистичн\w*)\b"
)


def _field(article: Any, key: str) -> str:
    try:
        return str(article[key] or "")
    except (KeyError, IndexError, TypeError):
        return str(getattr(article, key, "") or "")


def source_study_findings_2347(article: Any) -> tuple[str, ...]:
    """Extract at most 3 verbatim, early study-outcome sentences.

    With long review articles, standard relevance-scored evidence packs may
    capture sampling/methodology but omit measured results entirely.
    """
    title = _field(article, "title")
    raw = _field(article, "raw_text")
    if (len(raw) < 3000 or not _TITLE_RESEARCH.search(title)
            or not _SOURCE_METHOD.search(raw[:14000])):
        return ()
    sentences = _SENTENCE_BREAK.split(" ".join(raw[:14000].split()))
    found: list[str] = []
    for sentence in sentences:
        sentence = sentence.strip()
        if (50 <= len(sentence) <= 440
                and _SOURCE_FINDING.search(sentence)
                and sentence not in found):
            found.append(sentence)
            if len(found) == 3:
                break
    return tuple(found) if len(found) >= 2 else ()


def study_results_guidance_2347(article: Any) -> str:
    findings = source_study_findings_2347(article)
    if not findings:
        return ""
    quotes = "\n".join(f"- SOURCE RESULT {i}: {s}" for i, s in enumerate(findings, 1))
    return (
        "ДЖЕРЕЛЬНІ РЕЗУЛЬТАТИ ДОСЛІДЖЕНЬ (дослівні фрагменти ORIGINAL SOURCE, "
        "НЕ готовий пост):\n"
        + quotes
        + "\nОБОВ'ЯЗКОВО: якщо описуєш вибірку/метод/тривалість експерименту, "
        "вкажи принаймні ОДИН його конкретний виміряний результат, "
        "об'єкт оцінювання та напрям/відсутність ефекту. "
        "Не підміняй результат фразою «вплив неоднозначний», «дослідники "
        "досліджували», «результати обговорювали». Якщо в обсязі 900 символів "
        "бракує місця, прибери другорядну методику, а не висновок. "
        "Зберігай обмеження й невизначеність джерела.\n"
    )


def study_results_missing_2347(article: Any, final: str) -> str:
    """Reject only source-proven methods-only study coverage.

    An article without sufficiently verified source findings, or an overview
    that does not try to report the study methodology, is not hard-vetoed.
    """
    if not source_study_findings_2347(article):
        return ""
    text = str(final or "").strip()
    if not _METHODS_UA.search(text):
        return ""
    for sentence in _SENTENCE_BREAK.split(" ".join(text.split())):
        if _DIRECTION_UA.search(sentence) and _MEASURE_UA.search(sentence):
            return ""
    return "STUDY_RESULTS_MISSING_2347: описано учасників/метод, але не наведено конкретного результату дослідження"
