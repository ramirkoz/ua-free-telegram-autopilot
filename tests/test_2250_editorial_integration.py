"""2.2.50: prove the blueprint is wired to BOTH live editorial AI stages."""
import inspect

from telegram_autopilot.v2.editorial import EditorialEngine


def test_live_writer_has_source_bounded_blueprint_in_prompt():
    text = inspect.getsource(EditorialEngine.write)
    assert "build_editorial_blueprint(" in text
    assert "angle=selection.angle" in text
    assert "blueprint.prompt_block()" in text
    assert "source_fact_card.text" in text
    assert "editorial_angle=selection.angle" in text


def test_final_editor_reuses_angle_and_does_not_bypass_source_or_qa():
    text = inspect.getsource(EditorialEngine._final_edit)
    assert "build_editorial_blueprint(" in text
    assert "angle=editorial_angle" in text
    assert "blueprint.prompt_block(final=True)" in text
    assert "source_fact_card.text" in text
    assert "validator(candidate)" in text
    assert "validate_writer_output(" in text


def test_monitoring_readers_not_forced_through_extra_final_ai_calls():
    from telegram_autopilot.v2.reader_first import requires_final_reader_copyedit
    assert not requires_final_reader_copyedit(monitoring=True, legacy_quality_risk=False)
    assert requires_final_reader_copyedit(monitoring=True, legacy_quality_risk=True)
    assert requires_final_reader_copyedit(monitoring=False, legacy_quality_risk=False)
