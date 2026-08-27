from __future__ import annotations

import re

_INSTALLED = False


def _row_text(article, key: str) -> str:
    try:
        return str(article[key] or "")
    except Exception:
        return ""


def install_rc45_fact_guard() -> None:
    """Extend the established Fact Guard for Ukrainian/Russian -> English output."""
    global _INSTALLED
    if _INSTALLED:
        return

    from .fact_guard import FactGuardError
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
        assessment = original(article, output)
        source = " " + " ".join((_row_text(article, "title"), _row_text(article, "raw_text"))).casefold() + " "
        out = str(output or "")

        for pattern, source_signals, label in claim_rules:
            if pattern.search(out) and not any(signal.casefold() in source for signal in source_signals):
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

        return assessment

    policy.validate_fact_guard = validate_fact_guard_rc45
    _INSTALLED = True
