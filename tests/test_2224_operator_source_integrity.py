"""P0 overnight acceptance cases from source operator 2026-10-23."""
from telegram_autopilot.v2.editorial_hard_floor import facts,two_sentence_reason,fabricated_event_reason
from telegram_autopilot.v2.editorial import hard_editorial_reject, EditorialEngine
from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode, ChannelPolicy, Decision

def row(raw, title=""):
    return {"id":76242,"raw_text":raw,"title":title,"source_url":"https://t.me/test/4656"}

def ch(mode=ChannelMode.MONITORING):
    return ChannelConfig(id=3,name="ЗАПОРІЖЖЯ | ГРОМАДИ",telegram_chat_id="-1000",mode=mode,policy=ChannelPolicy(channel_id=3))

def test_short_one_sentence_no_inventing_another():
    assert two_sentence_reason(row("Через міст пролетіла реактива.")) == "EDITORIAL_MIN_TWO_SENTENCES: source"
    assert hard_editorial_reject(ch(),row("Через міст пролетіла реактива.")) == "EDITORIAL_MIN_TWO_SENTENCES: source"
    assert EditorialEngine.select(object.__new__(EditorialEngine),ch(),row("Через міст пролетіла реактива.")).decision==Decision.REJECT

def test_source_and_final_gates_separate():
    x=row("Міська рада ухвалила рішення. У понеділок запрацює ЦНАП.")
    assert two_sentence_reason(x)==""
    assert two_sentence_reason(x,"Міська рада ухвалила рішення.")=="EDITORIAL_MIN_TWO_SENTENCES: final"

def test_punctuation_title_footer_and_long_sentence_not_counted():
    assert len(facts("Міська рада повідомила про рішення. Джерело: https://t.me/test/1"))==1
    assert len(facts("Сьогодні у місті відбулися консультації за участю громадських організацій і місцевої влади."))==1

def test_abbreviations_not_extra_sentences():
    assert len(facts("У м. Запоріжжя відкрили центр. Відвідувачів приймають щодня."))==2

def test_fabricated_traffic_bridge_from_aircraft_route():
    x=row("Реактивний об’єкт пролетів через мости. Триває спостереження.")
    assert fabricated_event_reason(x,"Перекрили рух через мости. Рух відновлять після ремонту.") == "MONITORING_UNSETTLED_AERIAL_SOURCE"

def test_bare_aerial_bulletin_not_recast():
    x=row("Реактива кружляє над містами. Загроза ще триває.")
    assert fabricated_event_reason(x,"Два літаки вилетіли із Запоріжжя. Вони повертаються.")=="MONITORING_UNSETTLED_AERIAL_SOURCE"

def test_third_victim_not_automatically_family():
    x=row("Загинули чоловік і дружина. Також загинула 69-річна жінка.")
    assert fabricated_event_reason(x,"Загинули троє людей. Це була одна родина.")=="FACT_UNSUPPORTED_GROUP_KINSHIP"

def test_two_actual_facts_supported():
    x=row("У громаді відкрили ЦНАП. Прийом розпочинається у понеділок.")
    assert two_sentence_reason(x,"У громаді відкрили ЦНАП. Прийом розпочинається у понеділок.")==""
