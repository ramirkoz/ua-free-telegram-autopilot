from telegram_autopilot.v2.claim_trace import trace_output_claims


def test_exact_sourced_sentence_has_exact_offsets():
    original = "У громаді провели зустріч. Працював молодіжний центр."
    report = trace_output_claims(original, "У громаді провели зустріч.", source_id="community/1")
    assert len(report.statements) == 1
    assertion = report.statements[0]
    assert assertion.status == "EXACT"
    assert original[assertion.source_start:assertion.source_end] == assertion.source_quote
    assert not report.unresolved


def test_unsubstantiated_negative_aftermath_is_shadow_flagged():
    original = "РСЗВ вдарило по Юр'ївці."
    rewritten = "РСЗВ вдарило по Юр'ївці. Дані про постраждалих не надходили."
    report = trace_output_claims(original, rewritten, source_id="community/2")
    assert len(report.unresolved) == 1
    assert "не надходили" in report.unresolved[0].text


def test_legitimate_paraphrase_is_aligned_not_blocked():
    original = "Пошкодження будівлі підтвердили представники міської адміністрації."
    rewritten = "Представники міської адміністрації підтвердили пошкодження будівлі."
    report = trace_output_claims(original, rewritten, source_id="community/3")
    assert report.statements[0].status == "ALIGNED"
    assert not report.unresolved


def test_unrelated_story_is_unresolved():
    report = trace_output_claims(
        "На мосту сталася ДТП.",
        "Молодіжний центр організував творчий фестиваль.",
        source_id="community/4",
    )
    assert report.statements[0].status == "UNRESOLVED"
