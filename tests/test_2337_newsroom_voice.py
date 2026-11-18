"""2.3.37 style contract: writer + final editor on all three channel roles.

No live LLMs, operator data or publication side effects in this suite.
"""
from __future__ import annotations

import inspect
import pytest

from telegram_autopilot.v2.editorial import EditorialEngine
from telegram_autopilot.v2.editorial_voice_2337 import newsroom_voice_2337, needs_voice_editor_2337


@pytest.mark.parametrize("kwargs,role,excluded", [
    ({"science":True},"CTRL+UA","КРЕАТИВ, ДИЗАЙН"),
    ({"commercial":True},"ПРОДАНО!","РЕГІОНАЛЬНА ЖУРНАЛІСТИКА"),
    ({"monitoring":True},"ГРОМАДИ","НАУКА І ТЕХНОЛОГІЇ"),
])
def test_each_channel_gets_its_own_newsroom_voice(kwargs,role,excluded):
    block=newsroom_voice_2337(**kwargs)
    assert role in block
    assert excluded not in block
    assert "ОДИН головний підтверджений факт" in block
    assert "Не конспектуй SOURCE" in block
    assert "не вигадуй" in block.lower()


def test_monitoring_rejects_funny_or_bureaucratic_recasting_without_new_facts():
    block=newsroom_voice_2337(monitoring=True,final=True)
    assert "наради" in block
    assert "без метафор і жартів" in block
    assert "Не перетворюй сумнівний допис" in block
    assert "точно" in block
    assert "КОЖНЕ твердження з SOURCE" in block


def test_science_writer_leads_with_fact_not_chronological_paper_summary():
    block=newsroom_voice_2337(science=True)
    assert "ДОКАЗОВИЙ результат" in block
    assert "перелік методів" in block
    assert "побутові поради" in block


def test_creative_writer_focuses_on_original_mechanism_not_spec_sheet():
    block=newsroom_voice_2337(commercial=True)
    assert "сама" not in block[:10]  # not a canned headline
    assert "технічні характеристики".casefold() in block.casefold()
    assert "НЕ реанімуй" in block
    assert "авторських намірів" in block


def test_final_edit_has_real_restructuring_mandate_and_no_fact_bypass():
    block=newsroom_voice_2337(science=True,final=True)
    assert "ПЕРЕБУДУЙ" in block
    assert "перевіреної думки" in block
    assert "посилень упевненості" in block
    assert "не переписуй заради переписування" in block


@pytest.mark.parametrize("monitoring,short,long", [
    (False,319,320),
    (True,379,380),
])
def test_style_editor_cost_guard_on_substantive_posts_only(monitoring,short,long):
    assert not needs_voice_editor_2337("Ж"*short,monitoring=monitoring)
    assert needs_voice_editor_2337("Ж"*long,monitoring=monitoring)
    assert not needs_voice_editor_2337("",monitoring=monitoring)


def test_existing_writer_and_trusted_editor_receive_voice_and_fact_qa_remains():
    writer=inspect.getsource(EditorialEngine.write)
    final=inspect.getsource(EditorialEngine._final_edit)
    assert "newsroom_voice_2337(" in writer and "{newsroom_voice}" in writer
    assert "newsroom_voice_2337(" in final and "{newsroom_voice}" in final
    assert "needs_voice_editor_2337(" in writer
    assert "needs_trusted_editor" in writer and "trusted_only=True" in writer
    assert "validate_writer_output(" in writer
    assert "validate_writer_output(" in final
    assert "draft_final_regressions(" in final
    assert "non_overridable_quality_issues" in writer
    assert "GatewayExhausted" in writer


def test_no_new_model_or_database_dependency_in_voice_module():
    import telegram_autopilot.v2.editorial_voice_2337 as v
    src=inspect.getsource(v)
    assert "sqlite3" not in src
    assert "requests." not in src
    assert "gateway.run(" not in src
    assert "from .storage" not in src
    assert "telegram.send" not in src
