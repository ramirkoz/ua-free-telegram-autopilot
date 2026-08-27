from __future__ import annotations

import re

_INSTALLED = False
_CYR = re.compile(r"[А-Яа-яІіЇїЄєҐґЁёЫыЭэЪъ]")
_LAT = re.compile(r"[A-Za-z]")


def _row_text(article, key: str) -> str:
    try:
        return str(article[key] or "")
    except Exception:
        return ""


def _cross_language_source(source: str, output: str) -> bool:
    """True for Cyrillic UA/RU source -> predominantly English output.

    The established Fact Guard's Latin-token entity check is correct for
    English -> Ukrainian because product/model names normally remain Latin in both
    texts. It is not valid for UA/RU -> English: ordinary translated words and
    transliterated names naturally appear in Latin only in the output.
    """
    source_cyr = len(_CYR.findall(source))
    source_lat = len(_LAT.findall(source))
    out_cyr = len(_CYR.findall(output))
    out_lat = len(_LAT.findall(output))
    return source_cyr >= 40 and source_cyr > source_lat * 1.5 and out_lat >= 80 and out_lat > out_cyr * 4


def install_rc45_fact_guard() -> None:
    """Extend factual guards for Ukrainian/Russian -> English output."""
    global _INSTALLED
    if _INSTALLED:
        return

    from .fact_guard import FactGuardAssessment, FactGuardError
    from . import rc45_policy as policy

    original = policy.validate_fact_guard

    claim_rules = (
        (
            re.compile(r"\b(?:first-ever|world(?:'s)? first|for the first time|the first)\b", re.I),
            (" first ", "first-ever", "world's first", "world first", "for the first time", " вперше", " перш", " впервые", " перв"),
            "first/first-ever",
        ),
        (
            re.compile(r"\b(?:largest|biggest)\b", re.I),
            ("largest", "biggest", "найбільш", "найбіль", "крупнейш", "самый большой"),
            "largest/biggest",
        ),
        (
            re.compile(r"\bfastest\b", re.I),
            ("fastest", "найшвидш", "самый быст", "быстрейш"),
            "fastest",
        ),
        (
            re.compile(r"\bmost powerful\b", re.I),
            ("most powerful", "найпотужн", "самый мощн", "мощнейш"),
            "most powerful",
        ),
        (
            re.compile(r"\brecord(?:-breaking| setting)?\b", re.I),
            ("record", "рекорд"),
            "record",
        ),
    )

    def validate_fact_guard_rc45(article, output: str):
        source_original = " ".join((_row_text(article, "title"), _row_text(article, "raw_text")))
        source = " " + source_original.casefold() + " "
        out = str(output or "")

        # Preserve the mature RC40 guard for same-script/English-source flows.
        # In the reverse cross-language flow its Latin-entity set is not a valid
        # equivalence test, so use the dedicated relation/claim guards below while
        # number/year validation remains mandatory in rc45_policy.
        if _cross_language_source(source_original, out):
            assessment = FactGuardAssessment(checked_entities=0, checked_claims=0)
        else:
            assessment = original(article, out)

        checked_claims = int(getattr(assessment, "checked_claims", 0) or 0)
        for pattern, source_signals, label in claim_rules:
            if not pattern.search(out):
                continue
            checked_claims += 1
            if not any(signal.casefold() in source for signal in source_signals):
                raise FactGuardError(f"AI strengthened a source claim without evidence: {label}.")

        output_low = out.casefold()
        # Do not turn a Ukrainian/Russian agreement, plan or deployment into an
        # English purchase/acquisition claim unless the source itself says that.
        purchase_output = (" bought ", " purchased ", " acquired ", " acquisition ", " purchase ")
        source_purchase = (
            " buy ", " bought ", " purchase", " acquire", " acquisition",
            " купив", " купила", " купили", " придбав", " придбала", " придбали", " купівл",
            " купил", " купила", " купили", " приобрел", " приобрёл", " приобрела", " покупк",
        )
        source_deal = (
            " agreement", " deal ", " develop", " deploy", " plan ",
            " угод", " домовлен", " розгорт", " план",
            " соглаш", " договор", " разверт", " план",
        )
        if any(word in f" {output_low} " for word in purchase_output):
            if any(sig in source for sig in source_deal) and not any(sig in source for sig in source_purchase):
                raise FactGuardError("AI strengthened an agreement/plan/deployment into a purchase or acquisition.")

        return FactGuardAssessment(
            checked_entities=int(getattr(assessment, "checked_entities", 0) or 0),
            checked_claims=checked_claims,
        )

    policy.validate_fact_guard = validate_fact_guard_rc45
    _INSTALLED = True
