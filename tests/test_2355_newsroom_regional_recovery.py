"""2.3.55 regression: exact owner constraints, no operator mutation or Telegram.

Cohort source shapes reproduce REAL anonymous 2.3.54 failure classes from
read-only log: rich source -> short final, short nominal source,
dangling legal-aid footer, source-author community name, and 900 caption.
"""
from __future__ import annotations
from types import SimpleNamespace

import pytest

from telegram_autopilot.v2.domain import ChannelConfig,ChannelMode,ChannelPolicy
from telegram_autopilot.v2.editorial import _monitoring_limits,validate_writer_output,_rc111_prepare_candidate
from telegram_autopilot.v2.monitoring_short_material_2352 import monitoring_short_material_reason_2352, regional_publication_floor_2355
from telegram_autopilot.v2.terminal_repair_2355 import remove_orphaned_terminal_callout_2355
from telegram_autopilot.v2.terminal_text_guard_228 import incomplete_terminal_text_228
from telegram_autopilot.v2.source_attribution import source_body_attribution_issues,source_body_hard_limit
from telegram_autopilot.v2.quality_code_2355 import terminal_quality_code_2355
from telegram_autopilot.v2.story_brief_2355 import build_story_brief_2355


def chan(i=3, min_chars=500,max_chars=750, mode=ChannelMode.MONITORING):
    return ChannelConfig(id=i,name="ГРОМАДИ" if i==3 else "CTRL+UA",telegram_chat_id="@test",
        mode=mode,policy=ChannelPolicy(target_min_chars=min_chars,target_max_chars=max_chars))


def art(raw,**kw):
    return SimpleNamespace(id=101,title=raw[:60],raw_text=raw,source_name=kw.get('source_name',''),
        source_url='https://t.me/source/1',canonical_source_url='https://t.me/source/1')

# A well-sourced wartime local report includes distinct specific facts; it is
# NOT a license to generate 500+ characters from a one-sentence slogan.
REGIONAL_REPORT = (
    'У ніч на 24 листопада російські військові атакували Запоріжжя керованими авіабомбами та безпілотниками. '
    'За інформацією обласної прокуратури, загинули двоє людей — чоловік і жінка. '
    'Станом на 9:10 повідомили про 40 поранених, зокрема про немовля та дітей віком 4, 6 і 16 років. '
    'Зруйновано приватні будинки, пошкоджено багатоквартирні будинки та транспортні засоби. '
    'За процесуального керівництва прокурорів обласної прокуратури розпочали розслідування за статтею 438 КК України. '
    'Досудове розслідування здійснюють слідчі Управління СБУ в Запорізькій області. '
)


def test_regional_single_floor_for_writer_final_publisher():
    a=art(REGIONAL_REPORT)
    assert len(REGIONAL_REPORT)>500
    assert regional_publication_floor_2355(chan())==0
    assert _monitoring_limits(chan(),a,850)[0] < 500
    assert _monitoring_limits(chan(),a,850)[2] <= 850
    assert monitoring_short_material_reason_2352(chan(),a)==''
    with pytest.raises(ValueError,match='надто коротко'):
        validate_writer_output(a, 'У Запоріжжі сталася атака. '+('Пошкоджені будинки. '*21),
            min_chars=500,max_chars=750,hard_max_chars=750,strict_min_chars=True)


def test_no_cross_channel_floor_or_padding():
    a=art('Повідомили про коротку подію.')
    assert monitoring_short_material_reason_2352(chan(),a)==''
    assert regional_publication_floor_2355(chan(i=1,mode=ChannelMode.EDITORIAL))==0
    assert regional_publication_floor_2355(chan(min_chars=300))==0
    assert monitoring_short_material_reason_2352(chan(min_chars=300),a)==''
    assert _monitoring_limits(chan(),a,850)[1]<500  # source never admitted for writing


def test_region_real_525_draft_not_undercut_by_402_final():
    source=(
      'Внаслідок ударів керованими авіабомбами по Запоріжжю загинули двоє людей, ще 41 людина травмована. '
      'Серед постраждалих немовля та діти віком 4, 6 і 16 років. '
      'Рятувальники визволили із заблокованих квартир 15 мешканців. '
      'За однією адресою частково зруйнований перший поверх дев’ятиповерхового будинку. '
      'Одна з авіабомб влучила у п’ятиповерхівку. Пошкоджені сусідні будинки та понад десять автомобілів. '
      'За іншою адресою повністю зруйновано приватний будинок. Рятувальники загасили автомобіль. '
      'Уламками пошкоджені сусідні житлові будівлі. '
    )
    assert len(source)>=500
    final_short='У Запоріжжі внаслідок ударів загинули двоє людей. '+'Пошкоджені будинки. '*14
    assert len(final_short)<500
    assert monitoring_short_material_reason_2352(chan(),art(source),final_short)==''
    with pytest.raises(ValueError,match='надто коротко'):
        validate_writer_output(art(source),final_short,min_chars=500,max_chars=750,
                               hard_max_chars=750,strict_min_chars=True)


def test_orphan_tail_repair_uses_only_existing_complete_sentences():
    ready=(
      'Ветерани війни та члени сімей загиблих Захисників мають право на безоплатну правничу допомогу. '
      'Адвокат системи може представляти їхні інтереси в суді, допомогти скласти позов або заяву. '
      'Для звернення потрібні документ, що посвідчує особу, податковий номер і підтвердження статусу. '
      'Звернутися можна особисто до центру, через офіційні онлайн-канали або за телефоном 0 800 213 103. '
      'Підтверджені правила стосуються правничих послуг у цивільних і адміністративних справах. '
      'Додаткові консультації надають у межах системи безоплатної правничої допомоги. '
    )
    assert len(ready)>=500
    dangling=ready+'Інформація про право на допомогу:'
    fixed=remove_orphaned_terminal_callout_2355(dangling,min_chars=500)
    assert fixed==ready.strip()
    assert incomplete_terminal_text_228(fixed)==''
    assert remove_orphaned_terminal_callout_2355('Інформація про допомогу:',min_chars=500)=='Інформація про допомогу:'
    assert remove_orphaned_terminal_callout_2355('Коротка подія. Контакти:',min_chars=500)=='Коротка подія. Контакти:'
    assert remove_orphaned_terminal_callout_2355(ready+'Сторінка: https://example.org/',min_chars=500)==ready+'Сторінка: https://example.org/'


def test_source_owned_community_actor_allowed_but_fake_mention_banned():
    source='Великобілозерська громада долучається до кампанії «16 днів проти насильства». '
    actor='Великобілозерська громада долучилася до кампанії проти насильства.'
    a=art(source,source_name='Великобілозерська громада')
    assert source_body_attribution_issues(chan(),a,actor)==()
    assert source_body_attribution_issues(chan(),a,'За даними Великобілозерської громади, до кампанії долучилися учасники.')
    assert source_body_attribution_issues(chan(),art('Інша громада долучилася до акції.',source_name='Великобілозерська громада'),actor)


def test_900_caption_including_footer_and_newsroom_no_invented_facts():
    c=chan(i=1,mode=ChannelMode.EDITORIAL)
    a=art('Телескоп знайшов об’єкт у космосі.',source_name='Видання «Джерело»')
    limit=source_body_hard_limit(c,a,telegram_limit=900,default_body_limit=880)
    assert limit<=900
    brief=build_story_brief_2355(a,monitoring=False,science=True,commercial=False)
    assert brief.role=='science'
    assert all(hint in a.raw_text for hint in brief.hints)
    assert 'НЕПРОФІЛЬНОГО' in brief.prompt_block()


def test_exhausted_quality_reason_reports_actual_issue():
    assert terminal_quality_code_2355('TRUNCATED_TERMINAL_PUNCTUATION_228','кінець обірваний')=='PREPUBLISH_TERMINAL_BLOCKED_2355'
    assert terminal_quality_code_2355('PREPUBLISH_QA','текст обірваний')=='PREPUBLISH_TERMINAL_BLOCKED_2355'
    assert terminal_quality_code_2355('TELEGRAM_OVERSIZE','too long')=='TELEGRAM_OVERSIZE_BLOCKED'
    assert terminal_quality_code_2355('PREPUBLISH_SOURCE_SAFETY','unsupported claim')=='SOURCE_FACT_QA_BLOCKED'
    assert terminal_quality_code_2355('PREPUBLISH_QA','incoherent paragraph')=='PREPUBLISH_QA_BLOCKED'


def test_regional_end_to_end_writer_rejects_editor_shrink_and_keeps_verified_draft():
    """No API, no SQLite and no Telegram. Simulate old #112379 editor shrink."""
    from telegram_autopilot.v2.editorial import EditorialEngine, EditorialOutcome
    from telegram_autopilot.v2.domain import Decision
    from telegram_autopilot.v2.ai_gateway import GatewayExhausted
    source=(
        'Рятувальники деблокували із квартир у центрі Запоріжжя 15 людей після удару КАБами. '
        'Двоє людей загинули, ще 41 травмована, серед них немовля та діти віком 4, 6 і 16 років. '
        'За однією з адрес сталося влучання поряд із дев’ятиповерховим житловим будинком. '
        'Рятувальники вивільнили дев’ять мешканців із заблокованих квартир. '
        'Внаслідок удару частково зруйновано перший поверх, пошкоджено будинки й автомобілі. '
        'Одна авіабомба влучила у п’ятиповерхівку. За іншою адресою повністю зруйновано приватний будинок. '
        'Пошкоджено понад 10 автомобілів, рятувальники деблокували з-під завалів тіла двох загиблих. '
        'Пошкоджені сусідні будівлі, рятувальники ліквідували загоряння автомобіля. '
    )
    draft=(
        'Унаслідок ударів КАБами по центру Запоріжжя загинули двоє людей, ще 41 людина травмована. '
        'Серед постраждалих — немовля та діти віком 4, 6 і 16 років. '
        'Рятувальники визволили із заблокованих квартир 15 мешканців і деблокували з-під завалів тіла двох загиблих. '
        'В одному місці частково зруйнований перший поверх дев’ятиповерхового будинку. '
        'Авіабомба влучила у п’ятиповерхівку.\n\n'
        'Пошкоджені сусідні будинки та понад 10 автомобілів; за іншою адресою повністю зруйнований приватний будинок. '
        'Рятувальники загасили легковий автомобіль.'
    )
    assert len(source)>=500 and 500<=len(draft)<=750
    short_final='У центрі Запоріжжя відбувся удар. '+('Пошкоджені будинки. '*12)
    class FakeGateway:
        purposes=[]
        def run(self,prompt,validator=None,**kw):
            phase=kw.get('purpose')
            self.purposes.append(phase)
            value=draft if phase=='writer' else short_final
            try:
                if validator:
                    validator(value)
            except ValueError as exc:
                raise GatewayExhausted(str(exc),provider_outage=False) from exc
            return SimpleNamespace(text=value,provider='fixture',model='fixture')
    gateway=FakeGateway()
    engine=EditorialEngine.__new__(EditorialEngine)
    engine.gateway=gateway
    engine.learning=SimpleNamespace(style_memory_block=lambda *args:'')
    article=art(source)
    result=engine.write(chan(),article,EditorialOutcome(Decision.PUBLISH,angle=''))
    assert result.final_text==draft
    assert len(result.final_text)>=500
    assert 'writer' in gateway.purposes and 'final_editor' in gateway.purposes
