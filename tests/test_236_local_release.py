"""Safe release gates for 2.3.6 on exact operator 2.3.5 source.

No real API, Telegram sends, operator Data or Windows credentials are used.
"""
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

from telegram_autopilot.v2.storage import V2Store
from telegram_autopilot.v2.domain import ChannelMode, DedupeProfile, EditorialRuntimeProfile
from telegram_autopilot.v2.editorial_human_calibration_236 import (
    MARKER, MIGRATION_KEY, BACKUP_KEY, calibrated_editorial_role,
    apply_editorial_calibration_236, rollback_editorial_calibration_236,
)
from telegram_autopilot.v2.commercial_sources_235 import apply_commercial_sources_235
from telegram_autopilot.v2.commercial_feedburner_236 import restore_trend_hunter_236
from telegram_autopilot.v2.monitoring_civic_quality import civic_relevance_exclusion
from telegram_autopilot.v2.monitoring_live_now import live_now_exclusion
from telegram_autopilot.v2.event_dedupe_guard import event_fingerprint_same_event
from telegram_autopilot.v2.source_final_fidelity_255 import source_final_fidelity_issues


def _new_store(tmp_path):
    db = V2Store(tmp_path / "isolated_fixture.sqlite3")
    with db.transaction() as con:
        for cid, name, mode, profile, dedupe, named, compound in (
            (1,"CTRL+UA","editorial","standard","scientific_news",1,1),
            (2,"ПРОДАНО!","editorial","commercial_editorial","commercial_editorial",0,0),
            (3,"ЗАПОРІЖЖЯ | ГРОМАДИ","monitoring","standard","standard",0,0),
        ):
            con.execute(
                """INSERT INTO channels(id,name,channel_mode,editorial_runtime_profile,
                     dedupe_profile,dedupe_scientific_names,dedupe_compound_events,
                     created_at,updated_at) VALUES(?,?,?,?,?,?,?,'2026','2026')""",
                (cid,name,mode,profile,dedupe,named,compound),
            )
            con.execute(
                """INSERT INTO channel_policies(channel_id,purpose,audience,
                     selection_rules,rejection_rules,selector_extra_prompt,
                     writer_extra_prompt,updated_at)
                     VALUES(?,?,?,?,?,?,?,'2026')""",
                (cid, 'old purpose','old audience', 'old selected',
                 '[LIVE_NOW_RC96]' if cid==3 else 'old rejection',
                 'old selector', 'old writer'),
            )
        con.commit()
    return db


def test_policy_migration_scope_idempotence_and_rollback(tmp_path):
    db=_new_store(tmp_path)
    outcome=apply_editorial_calibration_236(db)
    assert outcome['count']==2 and sorted(outcome['roles']) == ['creative','science']
    with db.transaction() as con:
        rows={r['channel_id']:dict(r) for r in con.execute('SELECT * FROM channel_policies')}
        assert rows[1]['selection_rules'].startswith(MARKER)
        assert rows[2]['selection_rules'].startswith(MARKER)
        assert rows[3]['selection_rules'] == 'old selected'
        assert rows[3]['rejection_rules'] == '[LIVE_NOW_RC96]'
        assert 'цікаві' in rows[1]['purpose']
        previous=json.loads(con.execute('SELECT value FROM meta WHERE key=?',(BACKUP_KEY,)).fetchone()[0])
        assert previous['1']['purpose']=='old purpose'
        assert previous['2']['selector_extra_prompt']=='old selector'
        assert '3' not in previous
    assert apply_editorial_calibration_236(db)['count']==0
    assert rollback_editorial_calibration_236(db)==2
    with db.transaction() as con:
        assert con.execute('SELECT purpose FROM channel_policies WHERE channel_id=2').fetchone()[0]=='old purpose'
        assert not con.execute('SELECT value FROM meta WHERE key=?',(MIGRATION_KEY,)).fetchone()
    assert apply_editorial_calibration_236(db)['status']=='operator_rolled_back'


def test_old_full_profiles_not_retargeted_without_marker():
    c=SimpleNamespace(mode=ChannelMode.EDITORIAL,
                      editorial_runtime_profile=EditorialRuntimeProfile.STANDARD,
                      dedupe_profile=DedupeProfile.SCIENTIFIC_NEWS,
                      dedupe_scientific_names=True, dedupe_compound_events=True,
                      policy=SimpleNamespace(selection_rules='legacy'))
    assert not calibrated_editorial_role(c)
    c.policy.selection_rules=MARKER
    assert calibrated_editorial_role(c)=='science'
    c.mode=ChannelMode.MONITORING
    assert not calibrated_editorial_role(c)


def _src(con, sid, name, url, kind='rss', enabled=1):
    con.execute(
        """INSERT INTO sources(id,channel_id,name,url,kind,enabled,initialized,
         priority,legacy_config_json)
         VALUES(?,2,?,?,?,?,0,50,'{}')""",
        (sid,name,url,kind,enabled),
    )
    con.execute('INSERT INTO source_health(source_id) VALUES(?)',(sid,))


def test_235_bug_then_236_repair_retains_original_sources_and_receipts(tmp_path):
    db=_new_store(tmp_path)
    with db.transaction() as con:
        _src(con,199,'Yanko Design','https://www.yankodesign.com/feed/')
        _src(con,200,'Creative Bloq','https://www.creativebloq.com/feeds.xml')
        _src(con,201,'Design Milk','https://feeds.feedburner.com/design-milk')
        _src(con,202,'Muse by Clio','https://musebyclios.com/feed/')
        _src(con,127,'The Dieline','https://thedieline.com/',kind='page',enabled=0)
        _src(con,131,'Trend Hunter','https://www.trendhunter.com/',kind='page',enabled=0)
        con.commit()
    old=apply_commercial_sources_235(db)
    assert any(x.get('name')=='Trend Hunter' and x.get('reason')=='feed_host_in_use'
               for x in old['channels'][0]['skipped'])
    new=restore_trend_hunter_236(db)
    assert new['restored']==1
    assert restore_trend_hunter_236(db)['restored']==0
    with db.transaction() as con:
        trend=con.execute('SELECT * FROM sources WHERE id=131').fetchone()
        milk=con.execute('SELECT * FROM sources WHERE id=201').fetchone()
        assert trend['url']=='http://feeds.feedburner.com/TrendHunter/Top10'
        assert trend['enabled']==1 and milk['enabled']==1
        assert milk['url']=='https://feeds.feedburner.com/design-milk'
        assert con.execute('SELECT count(*) FROM sources WHERE channel_id=1').fetchone()[0]==0
        assert con.execute('SELECT count(*) FROM sources WHERE channel_id=3').fetchone()[0]==0


def test_manually_disabled_without_235_bug_marker_not_reenabled(tmp_path):
    db=_new_store(tmp_path)
    with db.transaction() as con:
        _src(con,131,'Trend Hunter','https://www.trendhunter.com/',kind='page',enabled=0)
        con.commit()
    assert restore_trend_hunter_236(db)['restored']==0


def _monitor():
    return SimpleNamespace(mode=ChannelMode.MONITORING,
        policy=SimpleNamespace(rejection_rules='[LIVE_NOW_RC96]'))


def test_morning_gromady_false_positives():
    ch=_monitor()
    assert civic_relevance_exclusion(ch,{'raw_text':
        'Демократична партія висунула найекстремальніших кандидатів в американській історії'})
    assert civic_relevance_exclusion(ch,{'raw_text':
        'По Борщагівці нічого не зрозуміло, схоже на ретельно сплановану підставу'})
    assert live_now_exclusion(ch,{'raw_text':
        'Ох ти! Яке сафарі по реактиву. Дуже чутно у Олександрівському.'})
    assert not civic_relevance_exclusion(ch,{'raw_text':
        'У Запоріжжі відбудеться зустріч громади про місцеві послуги'})


def test_power_outage_hours_must_survive_final():
    article={'raw_text':
        'Знову оновлено графіки відключень світла. Черга 1.1 з 09:00 до 13:00 '
        'з 16:00 до 20:00. Черга 1.2 з 08:00 до 12:00.'}
    vague='Оновлено графіки відключень: задіяні всі підчерги.'
    assert 'FACT_POWER_SCHEDULE_TIME_WINDOWS_LOST_236' in source_final_fidelity_issues(article,vague)
    exact='Черга 1.1 з 09:00 до 13:00 з 16:00 до 20:00, черга 1.2 з 08:00 до 12:00.'
    assert 'FACT_POWER_SCHEDULE_TIME_WINDOWS_LOST_236' not in source_final_fidelity_issues(article,exact)
    unrelated={'raw_text':'Засідання комісії: з 09:00 до 11:00 та з 13:00 до 15:00.'}
    assert not source_final_fidelity_issues(unrelated, 'Комісія провела засідання.')


SPORT_1='''Запорізькі спортсмени здобули медалі на змаганнях. Тхеквондо (Катар) — Максим Маненков срібло. Шашки (Нідерланди) — Богдан Панченков призер. Веслування (Аргентина) — Людмила Бабак бронза.'''
SPORT_2='''На чемпіонатах запорізькі спортсмени: Максим Маненков у Катарі з тхеквондо, Богдан Панченков у Нідерландах із шашок, Людмила Бабак в Аргентині з веслування, здобули нагороди.'''


def test_sports_cross_source_duplicate_and_distinct_competition():
    a={'raw_text':SPORT_1,'source_published_at':'2026-11-02T15:29:01+02:00'}
    b={'raw_text':SPORT_2,'source_published_at':'2026-11-02T15:44:58+02:00'}
    same,reason=event_fingerprint_same_event(a,b,monitoring_profile=True)
    assert same and 'SAME_MEDAL_DIGEST_236' in reason
    changed=dict(b, source_published_at='2026-11-09T15:44:58+02:00')
    assert not event_fingerprint_same_event(a,changed,monitoring_profile=True)[0]
    assert not event_fingerprint_same_event(a,b,monitoring_profile=False)[0]


def test_actual_235_editorial_selector_is_calibrated_and_does_not_run_old_value_veto():
    """The installed 2.3.5 has a direct EditorialEngine selector, not RC102 auto-install."""
    from telegram_autopilot.v2.editorial import EditorialEngine
    from telegram_autopilot.v2.domain import ChannelPolicy, Decision

    class Learning:
        def topic_assessment(self, cid, row):
            return SimpleNamespace(hard_suppress=False, fit_adjustment=0)
        def topic_memory_block(self, cid, row):
            return ""

    class Gateway:
        def __init__(self): self.prompts=[]
        def run(self, prompt, *, validator=None, **kwargs):
            self.prompts.append(prompt)
            assert kwargs['purpose']=='editorial_selector'
            assert kwargs['max_output_tokens']<=210
            payload='{"decision":"publish","fit_score":22,"reason":"цікава ідея","angle":"суть"}'
            if validator: validator(payload)
            return SimpleNamespace(text=payload,provider='mock',model='fixture')

    for cid,profile,dedupe in ((1,EditorialRuntimeProfile.STANDARD,DedupeProfile.SCIENTIFIC_NEWS),
                               (2,EditorialRuntimeProfile.COMMERCIAL_EDITORIAL,DedupeProfile.STANDARD)):
        engine=object.__new__(EditorialEngine)
        engine.learning=Learning()
        engine.gateway=Gateway()
        engine.store=None
        def _veto(*args,**kwargs): raise AssertionError('A second subjective veto must never run')
        engine._sold_value_allowed=_veto
        engine._value_allowed=_veto
        policy=ChannelPolicy(selection_rules=MARKER+' цікава новина',
             rejection_rules='відхиляй PR',purpose='допитливим',audience='читачі')
        channel=SimpleNamespace(id=cid,mode=ChannelMode.EDITORIAL,
             editorial_runtime_profile=profile,dedupe_profile=dedupe,
             dedupe_scientific_names=True,dedupe_compound_events=True,
             policy=policy)
        out=engine._select_editorial(channel,{'id':1000+cid,
            'title':'Цікавий новий продукт', 'raw_text':'Виробники зробили новий продукт із незвичною функцією. Автори підтвердили факти.',
            'source_name':'test'})
        assert out.decision==Decision.PUBLISH
        assert out.reason.startswith('HUMAN_EDITORIAL_236_PASS')
        assert len(engine.gateway.prompts)==1
        assert 'COMMERCIAL_READER_RULE_256' not in engine.gateway.prompts[0]
