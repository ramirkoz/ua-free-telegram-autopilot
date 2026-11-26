"""Reproduce verified 2.3.61 LIVE failures without API or operator Data."""
from datetime import datetime, timezone
from types import SimpleNamespace
import pytest
from telegram_autopilot.v2.numeric_grounding import unsupported_numbers
from telegram_autopilot.fact_guard import actionable_source_urls, strip_monitoring_nonform_urls, validate_fact_guard, FactGuardError
from telegram_autopilot.v2.editorial import restore_practical_literals
from telegram_autopilot.v2.ai_cost_2360 import compact_prompt
from telegram_autopilot.v2.creative_reader_2358 import creative_portfolio_reason
from telegram_autopilot.v2.ai_economics_237 import runtime_economics_snapshot
from telegram_autopilot.v2.storage import V2Store


def test_live_115303_joined_date_and_terminal_numbers():
    raw = 'Сергій Білов з квітня 2017 по квітень 2024 року працював в департаменті культури і туризму на керівних посадах.24 квітня 2024 року був затверджений заступником міського голови.'
    assert unsupported_numbers(raw, '24 квітня 2024 року його затвердили заступником міського голови.') == []
    assert unsupported_numbers(raw, '25 квітня 2024 року його затвердили.') == ['25']
    assert unsupported_numbers('Було 24.', 'Було 25.') == ['25']
    assert unsupported_numbers('Сума 1,24 та час 17:30.', 'Сума 24.') == ['24']


def test_live_115296_consultation_link_restored_and_preserved():
    url = 'https://business.diia.gov.ua/consultations'
    raw = 'Така підтримка допомагає підприємцям ухвалювати обґрунтовані управлінські рішення. Детальна інформація про сервіс та можливість запису на консультацію доступні за посиланням: ' + url + ' ' + url
    article = {'title':'Дія.Бізнес', 'raw_text':raw, 'source_url':'https://t.me/myrnenska/1961','canonical_source_url':'https://t.me/myrnenska/1961'}
    assert actionable_source_urls(raw)==[url]
    body='Підприємці можуть отримати консультації. Така підтримка допомагає ухвалювати рішення.'
    fixed=restore_practical_literals(article,body,hard_max_chars=880)
    assert fixed.count(url)==1
    assert url in strip_monitoring_nonform_urls(article,fixed)
    with pytest.raises(FactGuardError, match='практичне посилання'):
        validate_fact_guard(article,body+' '+url+'/wrong')
    validate_fact_guard(article,fixed)
    assert actionable_source_urls('Детальніше про це повідомляє джерело: https://example.org/news')==[]
    assert actionable_source_urls('Запис на консультацію: https://t.me/channel/123')==[]


def test_prompt_only_removes_redundant_literal():
    quote='Цей досить довгий дослівний фрагмент першоджерела описує перевірену подію.'
    missing='Інший довгий фрагмент не увійшов до обмеженого пакета джерела.'
    prompt=f'CHANNEL RULES: keep every material fact\n- Цитата SOURCE: {quote}\n- Цитата SOURCE: {missing}\nSOURCE:\n{quote}\nDRAFT:\n{quote}'
    out=compact_prompt(prompt)
    assert out.split('SOURCE:\n',1)[1]==prompt.split('SOURCE:\n',1)[1]
    assert missing in out and 'CHANNEL RULES:' in out
    assert len(out)<len(prompt)


def test_routine_retail_1479_with_related_cards():
    article={'title':'Lil Uzi Vert Weaves a Rainbow of Thread Into the Vans Authentic 44 Pink Cosmos','raw_text':'Footwear\nColorway: Pink/Multi-ColorSKU: VN0010WY3TD\nMSRP: TBC\nRelease Date: Holiday 2026\nThe pair arrives with woven threads, pink eyelets and logos. Read Full Article Related Stories: interactive inventions and accessible design.'}
    assert creative_portfolio_reason(article)=='CREATIVE_ROUTINE_RETAIL_LISTING_2362'
    assert not creative_portfolio_reason(dict(article,raw_text=article['raw_text'].replace('The pair arrives','The pair is made from recycled plastic. The pair arrives')))
    assert not creative_portfolio_reason({'title':'Headphones packaged in a bag of chips','raw_text':'An unusual packaging campaign.'})


def test_runtime_cost_window_does_not_mix_releases(tmp_path):
    store=V2Store(tmp_path/'db.sqlite3')
    with store.connect() as con:
        for at,cost in [('2026-11-26T09:00:00+00:00',.30),('2026-11-26T10:01:00+02:00',.40),('2026-11-26T11:01:00+02:00',.20),('2026-11-26T12:01:00+02:00',.90)]:
            con.execute('INSERT INTO ai_usage_events(created_at,provider,model,purpose,input_tokens,output_tokens,actual_openrouter_usd) VALUES(?,?,?,?,?,?,?)',(at,'openrouter','model','writer',100,30,cost))
    result=runtime_economics_snapshot(store,'2026-11-26T11:00:00+02:00',now=datetime(2026,11,26,10,0,tzinfo=timezone.utc))
    assert result['recorded_ai_calls']==2
    assert result['actual_openrouter_usd']==.50
    assert result['usd_per_committed_post'] is None
    assert runtime_economics_snapshot(store,'')['scope']=='not_running'


def test_service_links_and_glued_duplicate_115288_115224_115092():
    url='https://business.diia.gov.ua/consultations'
    raw='Детальніше про сервіс та запис на консультацію: '+url+' '+url+'Розвивайте власну справу!'
    assert actionable_source_urls(raw)==[url]
    assert actionable_source_urls('Як скористатися?1️⃣ Перейдіть на https://veteranpro.gov.ua/ veteranpro.gov.ua.2️⃣ Оберіть режим «AI».')==['https://veteranpro.gov.ua/']
    assert actionable_source_urls('Актуальні графіки відключень цілодобово – на нашому сайті на сторінці https://www.zoe.com.ua/outage/ Стабілізаційні відключення.')==['https://www.zoe.com.ua/outage/']
    assert not actionable_source_urls('Детальніше на нашому сайті: https://example.org/news')


def test_writer_checkpoint_exact_source_policy_prompt_and_cascade(tmp_path):
    from telegram_autopilot.v2.ai_cost_2360 import writer_checkpoint, save_writer_checkpoint, clear_writer_checkpoint
    store=V2Store(tmp_path/'db.sqlite3')
    from telegram_autopilot.v2.storage import now_iso
    with store.connect() as con:
        con.execute("INSERT INTO channels(id,name,created_at,updated_at) VALUES(1,'CTRL+UA',?,?)",(now_iso(),now_iso()))
        con.execute("INSERT INTO sources(id,channel_id,kind,name,url) VALUES(1,1,'rss','Science','https://example.org/feed')")
        row=con.execute('SELECT id,channel_id FROM sources LIMIT 1').fetchone()
    aid=store.insert_collected(channel_id=row['channel_id'],source_id=row['id'],external_id='2362-checkpoint',title='Source news',source_url='https://example.com/2362',raw_text='Source evidence.')
    article=store.get_article(aid)
    channel=SimpleNamespace(id=row['channel_id'],policy='policy1')
    save_writer_checkpoint(store,channel,article,'exact prompt','draft','openrouter','writer')
    assert writer_checkpoint(V2Store(store.path),channel,article,'exact prompt')==('draft','openrouter','writer')
    assert writer_checkpoint(store,channel,article,'changed prompt') is None
    assert writer_checkpoint(store,SimpleNamespace(id=row['channel_id'],policy='policy2'),article,'exact prompt') is None
    assert writer_checkpoint(store,channel,dict(article,raw_text='new source'),'exact prompt') is None
    clear_writer_checkpoint(store,aid)
    assert writer_checkpoint(store,channel,article,'exact prompt') is None
