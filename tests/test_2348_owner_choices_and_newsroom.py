"""2.3.48 source-only newsroom and human editorial signal tests."""
from telegram_autopilot.v2.monitoring_newsroom_2348 import source_non_news_reason_2348,robotic_lead_reason_2348,monitoring_newsroom_instruction_2348
from telegram_autopilot.v2.editorial_owner_choices_2348 import owner_choice_guidance_2348
def row(t,b):return {"title":t,"raw_text":b}
def test_community_ceremony():
 assert source_non_news_reason_2348(row("День громади","Вітаємо Роздольську громаду з Днем територіальної громади. Бажаємо миру, добра та успіху."))=="MONITORING_CEREMONIAL_GREETING_NO_EVENT_2348"
def test_hollow_protocol():
 assert source_non_news_reason_2348(row("Засідання Конгресу","Начальник МВА взяв участь у регіональному засіданні Конгресу. Обговорили бюджети, переселенців та важливість співпраці."))=="MONITORING_PROTOCOL_MEETING_NO_RESULT_2348"
def test_real_decision_overrides_protocol():
 assert source_non_news_reason_2348(row("Засідання ради","Начальник взяв участь у засіданні міської ради. Ухвалили рішення про виділення 200 тисяч гривень на ремонт укриття."))==""
def test_evacuation_survives():
 assert source_non_news_reason_2348(row("Евакуація","Під час зустрічі повідомили, що поліцейські евакуювали 19 людей, серед них 12 жінок. Звертайтеся за номером 102."))==""
def test_attack_survives():
 assert source_non_news_reason_2348(row("941 удар","У Запорізькій області поранені троє людей. Росіяни завдали 941 удар по 45 населених пунктах."))==""
def test_shelter_repair_survives():
 assert source_non_news_reason_2348(row("Укриття","У Запоріжжі завершили ремонт семи укриттів. Останнє розраховане на 250 людей."))==""
def test_actionable_service_overrides_greeting():
 assert source_non_news_reason_2348(row("День громади","Вітаємо з Днем громади. Відкрито прийом заявок, телефон 0800123456, з 9:00 до 16:00."))==""
def test_robotic_lead_soft_edit_only():
 assert robotic_lead_reason_2348("У межах реалізації проєкту було проведено засідання.")
 assert not robotic_lead_reason_2348("У Балабиному воду відключили на 15 вулицях.")
def test_journalist_instruction():
 assert "журналіст" in monitoring_newsroom_instruction_2348(row("Обстріл","Унаслідок атаки поранено троє людей. Пошкоджені будинки."),final=True)
def test_human_green_not_force_publish():
 assert "НЕ дозвіл" in owner_choice_guidance_2348("science")
 assert "ігрові" in owner_choice_guidance_2348("creative")
 assert owner_choice_guidance_2348("monitoring")==""
