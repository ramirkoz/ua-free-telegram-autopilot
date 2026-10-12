from types import SimpleNamespace
from telegram_autopilot.fact_guard import strip_monitoring_nonform_urls
from telegram_autopilot.v2.editorial import restore_practical_literals

SOURCE="https://forms.gle/ZurafEVbmhAytXxw8"
def article():
    return SimpleNamespace(raw_text="Шановні захисники! Заповніть анкету за посиланням: "+SOURCE+"\nІніціатива реалізується за підтримки партнерів", source_name="Терпіннівська громада", source_url="https://t.me/terpinne/99", title="Опитування ветеранів")

def test_210_correct_existing_form_not_duplicated():
    a=article()
    body="Опитування для ветеранів.\n\nАнкета: "+SOURCE
    assert restore_practical_literals(a,body,hard_max_chars=2000).count(SOURCE)==1
    assert strip_monitoring_nonform_urls(a,body).count(SOURCE)==1

def test_210_polluted_form_suffix_repaired_not_appended():
    a=article()
    body="Опитування для ветеранів.\n\nАнкета: "+SOURCE+"\n\nДеталі/реєстрація: "+SOURCE+"Ініціатива"
    cleaned=strip_monitoring_nonform_urls(a,restore_practical_literals(a,body,hard_max_chars=2000))
    assert cleaned.count(SOURCE)==1
    assert "Ініціатива" not in cleaned
    assert "Деталі/реєстрація" not in cleaned

def test_210_news_channel_cannot_be_registration():
    a=SimpleNamespace(raw_text="Читайте: https://t.me/five_redakcia",source_name="5 РЕДАКЦІЯ",source_url="https://t.me/five_redakcia/111211")
    assert "five_redakcia" not in strip_monitoring_nonform_urls(a,"Деталі/реєстрація: https://t.me/five_redakcia")
