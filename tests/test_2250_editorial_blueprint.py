"""Autopilot 2.2.50: editorial intent is source-based, role-scoped, cost-free."""
from telegram_autopilot.v2.editorial_blueprint_250 import build_editorial_blueprint


def article(title, raw):
    return {"title": title, "raw_text": raw}


def test_science_blueprint_prioritizes_readable_meaning_and_uncertainty():
    source = article(
        "Dying star offers a glimpse into our solar system",
        "Astronomers detected two rings around a white dwarf. Researchers suggest "
        "the shape might be maintained by surviving planetary bodies."
    )
    plan = build_editorial_blueprint(source, science=True, angle="Значення для людей")
    assert plan.kind == "science_insight"
    assert "відкриття" in plan.lead_task
    assert "припущення" in plan.hard_boundary
    assert "можливо" in plan.hard_boundary
    assert "Значення для людей" in plan.prompt_block()


def test_commercial_comparison_attributed_not_invented_intent():
    source = article(
        "Hand-drawn holiday campaign compared to AI ads",
        "A design publication compared a brand's traditional animation to an AI-generated ad."
    )
    plan = build_editorial_blueprint(source, commercial=True, angle="Ручна анімація як відмінність")
    assert plan.kind == "commercial_contrast"
    assert "атрибутуй" in plan.proof_order
    assert "не підтвердили" in plan.hard_boundary
    assert "РУЧНА" not in plan.prompt_block()  # no shouting or hallucinated copy


def test_commercial_basic_story_not_contrast_without_source_ai():
    plan = build_editorial_blueprint(
        article("Traditional hand-drawn animation", "The brand commissioned hand-painted work."),
        commercial=True,
    )
    assert plan.kind == "commercial_story"
    assert "атрибутуй" not in plan.proof_order


def test_civic_service_must_have_original_contacts():
    source = article(
        "Психологічна допомога", "Фонд пропонує безоплатні консультації онлайн. "
        "Звертайтеся за номером 0 800 300 415 або пишіть на info@example.org."
    )
    plan = build_editorial_blueprint(source, monitoring=True, angle="Маркетинговий конфлікт")
    assert plan.kind == "civic_service"
    assert "рядки контактів" in plan.proof_order
    assert "Маркетинговий" not in plan.prompt_block()
    assert "НЕ" not in plan.kind


def test_civic_alert_keeps_no_inferred_contact_format():
    plan = build_editorial_blueprint(
        article("Оперативна інформація", "Повідомлення про наслідки обстрілу без контактів."),
        monitoring=True
    )
    assert plan.kind == "civic_report"
    assert "телефони" not in plan.proof_order


def test_notice_format_not_mistaken_for_service():
    plan = build_editorial_blueprint(
        article("Рішення про графік", "Оприлюднено рішення про новий графік прийому."),
        monitoring=True,
    )
    assert plan.kind == "civic_notice"
    assert "підтверджену" in plan.lead_task


def test_article_substring_does_not_turn_plan_into_external_fact():
    source = article("Science finding", "Researchers may have detected another ring.")
    plan = build_editorial_blueprint(source, science=True, angle="Astronomers identified a giant dragon.")
    assert plan.kind == "science_insight"
    assert "ANGLE" not in plan.prompt_block()
    assert "лише якщо SOURCE його підтримує" in plan.prompt_block()


def test_blueprint_does_not_depend_on_numeric_channel_identity():
    source = article("Brand campaign", "The company launched an advertising campaign.")
    assert build_editorial_blueprint(source, commercial=True).kind == "commercial_story"
    assert build_editorial_blueprint(source, science=True).kind == "science_insight"
    assert build_editorial_blueprint(source, monitoring=True).kind == "civic_report"


def test_final_editor_reuses_identical_reading_mission():
    source = article("Маркетинг", "Агенція випустила рекламну кампанію.")
    plan = build_editorial_blueprint(source, commercial=True, angle="Ідея кампанії")
    assert "ПИТАННЯ ЧИТАЧА" in plan.prompt_block(final=True)
    assert "ФІНАЛЬНА ПЕРЕВІРКА" in plan.prompt_block(final=True)
    assert "Ідея кампанії" in plan.prompt_block(final=True)
