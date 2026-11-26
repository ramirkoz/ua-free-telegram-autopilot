from types import SimpleNamespace
import sqlite3
import pytest
from telegram_autopilot.v2 import provider_trial_2361 as trial
from telegram_autopilot.v2 import provider_api


def test_read_only_store_cannot_modify(tmp_path):
    path=tmp_path/'db.sqlite3'
    with sqlite3.connect(path) as con:
        con.execute('create table t(x)')
        con.execute('insert into t values (1)')
    store=trial.ReadOnlyStore(path)
    with store.connect() as con:
        assert con.execute('select x from t').fetchone()[0]==1
        with pytest.raises(sqlite3.OperationalError): con.execute('delete from t')
    with pytest.raises(RuntimeError): store.transaction()
    with pytest.raises(RuntimeError): store.initialize()


def test_capture_stops_before_network():
    w=trial.CaptureWriter()
    with pytest.raises(trial._WriterCaptured):
        w.run('source prompt', validator=lambda raw: None, max_output_tokens=1100, purpose='writer')
    assert w.prompt=='source prompt' and w.max_output_tokens==1100
    with pytest.raises(RuntimeError): w.run('other',validator=None,max_output_tokens=100,purpose='final_editor')


def test_paid_or_unknown_model_never_called():
    with pytest.raises(ValueError): trial.direct_reply('openrouter','test',None,None)
    with pytest.raises(ValueError): trial.direct_reply('gemini','unknown',None,None)


def test_gemini_exact_trial_does_not_fallback(monkeypatch):
    called=[]
    def fail(url,**kwargs):
        called.append(url)
        raise provider_api.ProviderAPIError('unsupported',kind='model')
    monkeypatch.setattr(provider_api,'_request_json',fail)
    with pytest.raises(provider_api.ProviderAPIError):
        provider_api.gemini_generate(model='gemini-3.5-flash',api_key='test',prompt='source',max_output_tokens=1100,timeout_seconds=35,exact_model=True)
    assert len(called)==1


def test_cli_requires_explicit_confirmation(tmp_path):
    with pytest.raises(SystemExit):
        trial.main(['--provider','gemini','--model','gemini-3.5-flash','--article','1','--output',str(tmp_path/'report.json')])
    assert not (tmp_path/'report.json').exists()


def test_real_writer_prompt_from_read_only_fixture(tmp_path, monkeypatch):
    from telegram_autopilot.v2.storage import V2Store, now_iso
    from telegram_autopilot.v2.domain import ChannelConfig, ChannelPolicy
    path=tmp_path/'operator.sqlite3'; store=V2Store(path)
    with store.connect() as con:
        con.execute("INSERT INTO channels(id,name,created_at,updated_at) VALUES(1,'CTRL+UA',?,?)",(now_iso(),now_iso()))
        con.execute("INSERT INTO sources(id,channel_id,kind,name,url) VALUES(1,1,'rss','Science','https://example.org/feed')")
    store.save_channel(ChannelConfig(id=1,name='CTRL+UA',telegram_chat_id='',policy=ChannelPolicy(channel_id=1,writing_rules='Тестове правило редакції')))
    aid=store.insert_collected(channel_id=1,source_id=1,external_id='sample',title='Дослідники перевірили новий матеріал',source_url='https://example.org/sample',raw_text='Дослідники перевірили новий матеріал. Вимірювання показали, що він витримує навантаження. ' * 8)
    store.update_article(aid, published_at=now_iso(), final_text='Збережений фінальний текст для порівняння.')
    ro=trial.ReadOnlyStore(path)
    before=path.read_bytes()
    seen=[]
    def fake(provider,model,cfg,writer):
        seen.append(writer.prompt)
        return SimpleNamespace(text='Not a Ukrainian post',model=model,input_tokens=20,output_tokens=5)
    monkeypatch.setattr(trial,'direct_reply',fake)
    row=trial.trial_article(ro,None,'gemini','gemini-3.5-flash',aid)
    assert len(seen)==1 and 'Тестове правило редакції' in seen[0] and 'Дослідники перевірили' in seen[0]
    assert row['status']=='qa_rejected' and not row['qa_pass']
    assert row['baseline_final']=='Збережений фінальний текст для порівняння.'
    assert path.read_bytes()==before
