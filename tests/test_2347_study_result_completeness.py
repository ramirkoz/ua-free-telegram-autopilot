"""2.3.47 P0 owner sample: a study methodology is not a news result."""
from telegram_autopilot.v2.study_result_completeness_2347 import (
    source_study_findings_2347,
    study_results_guidance_2347,
    study_results_missing_2347,
)


def _study() -> dict[str, str]:
    # Synthetic source with verbatim-like study signals, not a stored article or
    # an AI answer. Mimics the real two-decade GTA review's long context.
    background = (
        "Background about a research debate over how game play affects "
        "human emotions, aggression, and empathy across several decades. "
    ) * 35
    return {
        "title": "What two decades of psychology and neuroscience research say about game play",
        "raw_text": (
            background
            + "Researchers used a controlled experiment with 194 participants. "
            + "Students who played violently reported higher levels of anger afterward than controls. "
            + "Further statistical analysis indicated that this effect depended on immersion. "
            + "In a randomized trial with 135 students who played for 12 hours across three weeks, "
            + "researchers found no statistically significant differences in aggression or empathy "
            + "between players and the no-game control group. "
            + "Later results showed that some participants gave higher estimates of traffic deaths. "
        ),
    }


def test_real_owner_gta_1327_methods_only_cannot_publish():
    article = _study()
    failed = (
        "Два десятиліття досліджень не дали однозначної відповіді щодо впливу гри: "
        "деякі ефекти помічали за кілька хвилин, інші не виявляли навіть після місяців. "
        "Окремі результати ставали приводом для суперечок між дослідниками.\n\n"
        "В одному з експериментів 135 студентів університету випадково "
        "розподілили на групи. Половина грала в лабораторії "
        "12 годин протягом трьох тижнів."
    )
    assert study_results_missing_2347(article, failed).startswith("STUDY_RESULTS_MISSING_2347")


def test_revised_gta_with_source_supported_negative_finding_passes():
    article = _study()
    post = (
        "Після трьох тижнів гри дослідники не виявили статистично значущої "
        "різниці в агресії або емпатії між двома групами студентів. "
        "В іншому короткому експерименті рівень гніву був вищим "
        "після насильницької гри, ніж після боулінгу."
    )
    assert study_results_missing_2347(article, post) == ""


def test_source_outcomes_extract_both_anger_and_three_week_null_result():
    findings = source_study_findings_2347(_study())
    assert len(findings) == 3
    assert "reported higher levels of anger" in findings[0]
    assert "no statistically significant differences" in findings[1]


def test_briefing_is_original_source_only_with_no_claim_invention():
    a = _study()
    guidance = study_results_guidance_2347(a)
    assert "SOURCE RESULT" in guidance
    assert "no statistically significant differences" in guidance
    for quote in source_study_findings_2347(a):
        assert quote in a["raw_text"]
        assert quote in guidance


def test_no_trigger_when_news_is_not_a_research_article():
    a = _study()
    a["title"] = "New design of a gaming controller arrives in stores"
    assert source_study_findings_2347(a) == ()
    assert study_results_missing_2347(a, "В експерименті брали участь студенти.") == ""


def test_no_veto_if_source_has_only_methods_and_no_measured_findings():
    a = _study()
    a["raw_text"] = "People described a study with students and participants. " * 100
    assert source_study_findings_2347(a) == ()
    assert study_results_missing_2347(a, "У досліді брали участь учасники.") == ""


def test_no_veto_for_short_or_unrelated_research_notice():
    a = _study()
    a["raw_text"] = "Participants enrolled in a randomized experiment; results to follow."
    assert source_study_findings_2347(a) == ()
    assert study_results_missing_2347(a, "В експерименті взяли участь 12 людей.") == ""


def test_valid_summary_without_methodology_escapes_narrow_guard():
    a = _study()
    summary = "Тривалість гри не дозволяє зробити однозначний висновок з усіх наявних робіт."
    assert study_results_missing_2347(a, summary) == ""


def test_measured_hook_memory_result_is_not_overblocked():
    a = _study()
    a["title"] = "New psychology research sheds light on why pop song hooks stick in your head"
    a["raw_text"] += (
        "Another trial showed higher hook ratings after repeated listening. "
        "The auditory distraction decreased memory ratings."
    )
    post = (
        "Дослідження показало, що оцінки запам’ятовуваності "
        "музичних «гачків» зростали після повторного прослуховування. "
        "Під час експерименту студентів також відволікали словами."
    )
    assert study_results_missing_2347(a, post) == ""
