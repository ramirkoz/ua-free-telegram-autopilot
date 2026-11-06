"""Bounded editorial work-queue preference ordering for saturated 24h windows.

Only one low-cost headline hint in the SAME six-hour freshness tier.
This is not a publish decision: every article must still pass the AI selector,
Fact Guard, media, dedupe, TTL, source-start fence and delivery ledger.
"""


def priority_sort_sql_2316() -> str:
    """Return a fixed SQL expression over joined articles a and channels c.

    Rank 0 is a topical candidate, 1 neutral, 2 retail/newswire noise. It
    cannot compensate for a different age tier or bypass publisher interval.
    Scope only calibrated science and commercial editorial runtime profiles.
    """
    subject = "lower(coalesce(a.title,''))"
    science = (
        "('research','discovery','scientist','science','study','telescope',"
        "'spacecraft','space mission','planet','robot','artificial intelligence',"
        "'neural','quantum','cybersecurity','security flaw','experiment',"
        "'дослідж','відкрит','робот','космос','штучн','квантов')"
    )
    creative = (
        "('campaign','packaging','design','logo','brand identity','animation',"
        "'advertis','creative','prototype','redesign','invent','illustration',"
        "'дизайн','упаковк','анімаці','кампані','логотип','прототип')"
    )
    noise = (
        "('discount','coupon','black friday sale','job opening','appointment',"
        "'earnings report','limited-time deal','знижк','купони','вакансі')"
    )
    def contains_any(keys: str) -> str:
        # All terms are fixed literals, not user strings or dynamic SQL inputs.
        literals = [item.strip().strip("'") for item in keys.strip("()").split(",")]
        return "(" + " OR ".join(f"instr({subject},'{term}')>0"
                               for term in literals if term) + ")"
    good_science = contains_any(science)
    good_creative = contains_any(creative)
    noisy = contains_any(noise)
    return (
        "(CASE WHEN c.channel_mode<>'editorial' THEN 1 "
        f"WHEN {noisy} THEN 2 "
        f"WHEN c.editorial_runtime_profile='commercial_editorial' AND {good_creative} THEN 0 "
        f"WHEN c.dedupe_profile='scientific_news' AND {good_science} THEN 0 "
        "ELSE 1 END)"
    )
