"""2.3.11 LIVE-evidenced municipal scope and legal allegation integrity.

Source contents, not the source channel brand or a media link, determine
regional relevance. This module is deliberately narrow: ordinary civic
services, regional investigations and confirmed court judgments remain eligible.
"""
from __future__ import annotations

import re
from typing import Any

from .live_editorial_integrity_239 import _field, _LOCAL


_NATIONAL_ENFORCEMENT = re.compile(
    r"(?iu)\b(?:НАБУ|САП|Офіс\w*\s+Генеральн\w*\s+прокурор\w*|"
    r"Національн\w*\s+поліці\w*|СБУ)\b"
)
_UNADJUDICATED_CASE = re.compile(
    r"(?iu)\b(?:викрил\w*|розсліду\w*|підозрю\w*|"
    r"злочинн\w*\s+організаці\w*|шахрайськ\w*\s+колцентр\w*|"
    r"підкуп\w*|обвинувач\w*)\b"
)
_CRIMINAL_CONDUCT = re.compile(
    r"(?iu)\b(?:злочинн\w*|шахрайськ\w*|підкуп\w*|"
    r"наркотик\w*|викраденн\w*|хабар\w*|розкраданн\w*)\b"
)
_VERIFIED_COURT_VERDICT = re.compile(
    r"(?iu)\b(?:вирок\w*\s+суд\w*|суд\w*\s+визна\w*\s+винн\w*)\b"
)
_CATEGORICAL_GUILT = re.compile(
    r"(?iu)\b(?:організатором\s+(?:став|був)|"
    r"підкуповувал\w*|ошукувал\w*|"
    r"угрупованн\w*\s+забезпечувал\w*|"
    r"(?:учасник\w*|угрупованн\w*)\s+організовувал\w*|"
    r"злочинц\w*\s+привласнил\w*)\b"
)
_ATTRIBUTED_ALLEGATION = re.compile(
    r"(?iu)\b(?:за\s+(?:даними|версією|інформацією)\s+"
    r"(?:слідств\w*|набу|сап|прокуратур\w*|правоохоронц\w*)|"
    r"за\s+підозрою|"
    r"(?:набу|сап|прокуратур\w*|правоохоронц\w*)\s+"
    r"(?:повідомил\w*|заявил\w*)|"
    r"слідч\w*\s+(?:вважа\w*|стверджу\w*)|"
    r"згідно\s+з\s+версією\s+слідств\w*)\b"
)
_CHANNEL_PROMO_CUTOFF = re.compile(r"(?iu)\bми\s+в\s*[📱📲]")


def _source_body(article: Any) -> str:
    raw = re.sub(r"https?://\S+", " ", _field(article, "raw_text"))
    raw = _CHANNEL_PROMO_CUTOFF.split(raw, maxsplit=1)[0]
    return (_field(article, "title") + "\n" + raw).strip()


def national_criminal_case_without_local_2311(article: Any) -> str:
    """National investigation is not a Zaporizhzhia event by source branding."""
    source = _source_body(article)
    if not source or _LOCAL.search(source):
        return ""
    if (_NATIONAL_ENFORCEMENT.search(source)
            and _UNADJUDICATED_CASE.search(source)
            and _CRIMINAL_CONDUCT.search(source)):
        return "MONITORING_NONLOCAL_NATIONAL_CRIMINAL_CASE_2311"
    return ""


def unattributed_criminal_allegation_2311(article: Any, text: str) -> str:
    """Detect only explicit case reporting with definite allegations as guilt.

    A source may allege a crime, but neither a national agency's press release
    nor an editor's paraphrase constitutes a court finding. Statements sourced
    to the investigation are allowed; a final court verdict is a separate case.
    """
    source = _source_body(article)
    final = str(text or "").strip()
    if not source or not final:
        return ""
    if not (_NATIONAL_ENFORCEMENT.search(source)
            and _UNADJUDICATED_CASE.search(source)
            and _CRIMINAL_CONDUCT.search(source)):
        return ""
    if _VERIFIED_COURT_VERDICT.search(source):
        return ""
    if _CATEGORICAL_GUILT.search(final) and not _ATTRIBUTED_ALLEGATION.search(final):
        return "MONITORING_UNATTRIBUTED_CRIMINAL_ALLEGATION_2311"
    return ""


LEGAL_ALLEGATION_WRITER_RULE_2311 = (
    "ЮРИДИЧНА ТОЧНІСТЬ: якщо SOURCE переказує підозру НАБУ, САП, поліції "
    "чи іншого правоохоронного органу, пиши «За даними слідства», "
    "«НАБУ повідомило про підозру», «За версією правоохоронців». "
    "Не оголошуй людину організатором або учасником доведеного злочину "
    "без вироку суду. Якщо SOURCE є агрегатором, не називай його "
    "першоджерелом слідчих фактів; посилайся на вказаний у SOURCE орган. "
    "Не додавай невідомих прізвищ, географії, сум, мотивів чи доказів. "
)
