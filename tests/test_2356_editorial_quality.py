"""2.3.56 source-based, operator-approved editorial regressions (no network/Telegram)."""
from __future__ import annotations

from types import SimpleNamespace
import pytest

from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode, ChannelPolicy, EditorialRuntimeProfile
from telegram_autopilot.v2.editorial_human_calibration_236 import MARKER
from telegram_autopilot.v2.editorial_quality_2356 import (
    creative_routine_product_reason_2356, regional_non_news_reason_2356,
    source_browser_fishing_mechanic_2356, missing_visual_story_bridge_2356,
    visual_story_prompt_2356, REGIONAL_NEWS_VALUE_PROMPT_2356,
)
from telegram_autopilot.v2.editorial_source_topic_2319 import editorial_source_topic_reason_2319
from telegram_autopilot.v2.quote_repair_2356 import source_verified_guillemet_2356
from telegram_autopilot.v2.qa_adjacent_word_239 import repair_adjacent_repeated_word
from telegram_autopilot.v2.editorial import hard_editorial_reject, EditorialEngine


def article(title, raw, **k):
    return SimpleNamespace(title=title,raw_text=raw,source_name=k.get('source_name',''),
        source_url='https://example.org/news/one', id=456, media_json='[]')


def creative_channel():
    return ChannelConfig(id=2,name='ПРОДАНО!',telegram_chat_id='@dummy',
        mode=ChannelMode.EDITORIAL,
        editorial_runtime_profile=EditorialRuntimeProfile.COMMERCIAL_EDITORIAL,
        policy=ChannelPolicy(selection_rules=MARKER + ' creative'))


def region_channel():
    return ChannelConfig(id=3,name='ЗАПОРІЖЖЯ | ГРОМАДИ',telegram_chat_id='@dummy',
        mode=ChannelMode.MONITORING,
        policy=ChannelPolicy(target_min_chars=500,target_max_chars=750,
                             rejection_rules='[LIVE_NOW_RC96] news'))


BROWSER_GAME_SOURCE = (
    'INTERNET4 is a multiplayer game where up to eight friends share one browser. '
    'You can browse websites and go fishing on any site you open. '
    'It also features Wikipedia Challenge, drawing, and quizzes. '
    'The game launches on Steam on December 4, 2026.'
)
BAD_CAPTION = (
    'У майбутній грі INTERNET4 гравець і до восьми друзів зможуть разом '
    'переглядати сайти в одному браузері й грати в мініігри. '
    'Серед них — риболовля, малювання та вікторини на загальні знання. '
    'Ігри планують випустити у Steam 4 грудня 2026 року.'
)
GOOD_CAPTION = (
    'У грі INTERNET4 можна з друзями рибалити просто поверх відкритої '
    'вебсторінки. Гравці бачать звичайний сайт, але вудки та улов з’являються '
    'просто на ньому. Є також вікторини й спільне малювання.'
)


def test_internet4_source_owned_mechanic_recognized():
    a=article('New Steam game adds multiplayer minigames to the entire internet',BROWSER_GAME_SOURCE)
    assert source_browser_fishing_mechanic_2356(a)
    assert 'спільний браузер' in visual_story_prompt_2356(a,commercial=True)
    assert not visual_story_prompt_2356(a,commercial=False)


def test_owner_rejected_internet4_caption_is_explained_or_blocked():
    a=article('New Steam game adds multiplayer minigames to the entire internet',BROWSER_GAME_SOURCE)
    assert missing_visual_story_bridge_2356(a,BAD_CAPTION,commercial=True)=='CREATIVE_VISUAL_MECHANIC_UNEXPLAINED_2356'
    assert missing_visual_story_bridge_2356(a,GOOD_CAPTION,commercial=True)==''
    assert not missing_visual_story_bridge_2356(a,BAD_CAPTION,commercial=False)


def test_internet4_before_send_gate_also_rejects_inherited_ready():
    a=article('New Steam game adds multiplayer minigames to the entire internet',BROWSER_GAME_SOURCE)
    assert hard_editorial_reject(creative_channel(),a,BAD_CAPTION)=='CREATIVE_VISUAL_MECHANIC_UNEXPLAINED_2356'
    assert hard_editorial_reject(creative_channel(),a,GOOD_CAPTION)==''


def test_visual_gate_does_not_guess_media_or_ban_unrelated_games():
    a=article('Fishing game at a lake', 'A story about an anglerfish in the ocean and a fishing game.')
    assert not source_browser_fishing_mechanic_2356(a)
    assert not missing_visual_story_bridge_2356(a,'Гравці ловлять рибу у відеогрі.',commercial=True)
    a=article('A KFC edible GTA disc stunt','The fried chicken disc is an edible piece inspired by GTA 6.')
    assert not missing_visual_story_bridge_2356(a,'Курячий диск замість гри GTA 6.',commercial=True)


@pytest.mark.parametrize('title,raw',[ 
    ('Trader Joe’s New Holiday Shortbread Cookies Arrive in Stores',
     'The limited-time holiday cookies are available in stores for $4.99. Customers say they like the flavor.'),
    ('The New $3.99 Cookie Is Back This Season',
     'The snack is in stores this month and shoppers say they love its new taste. It costs $3.99.'),
    ('New Seasonal Chocolate Biscuit Flavour Sold for $5',
     'The seasonal cookies are available now at stores for $5 and fans say they taste great.'),
])
def test_seasonal_food_shelf_news_veto_before_paid_ai(title,raw):
    a=article(title,raw)
    assert creative_routine_product_reason_2356(a)=='CREATIVE_ORDINARY_SEASONAL_PRODUCT_2356'
    assert editorial_source_topic_reason_2319(creative_channel(),a)=='CREATIVE_ORDINARY_SEASONAL_PRODUCT_2356'
    assert hard_editorial_reject(creative_channel(),a)=='CREATIVE_ORDINARY_SEASONAL_PRODUCT_2356'


@pytest.mark.parametrize('title,raw',[ 
    ('Pocket Obscura pinhole camera printed in 3D','A six-gram camera made by an artist using 3D printing; no lens.'),
    ('Artist designed a kinetic sculpture made out of cookies','An interactive art installation uses moving mechanical edible forms.'),
    ('KFC Makes Edible GTA 6 Replacement Disc','KFC Spain created a physical parody gaming disc and game packaging.'),
    ('Trader Joe’s New Mechanical Interactive Cookie Art Installation',
     'The designer made an interactive sculpture and 3D-printed the installation. It is available in stores for $20.'),
    ('New Seasonal Product from an Independent Brand','A prototype uses an unusual mechanical transformation.')
])
def test_positive_nonroutine_and_owner_accepted_concepts_remain_allowed(title,raw):
    assert creative_routine_product_reason_2356(article(title,raw))==''


def test_regional_internal_week_recap_without_public_result_rejected():
    title='Тиждень початкової школи пройшов у нашій школі'
    raw=('Протягом тижня учні брали участь у цікавих іграх, вікторинах, '
         'квестах та майстер-класах. Вчителі провели тематичні уроки. '
         'Кожного дня діти веселилися, малювали та виконували завдання. ' * 4)
    a=article(title,raw)
    assert regional_non_news_reason_2356(a)=='MONITORING_INTERNAL_SCHOOL_WEEK_NO_PUBLIC_RESULT_2356'
    assert hard_editorial_reject(region_channel(),a)=='MONITORING_INTERNAL_SCHOOL_WEEK_NO_PUBLIC_RESULT_2356'
    engine=EditorialEngine.__new__(EditorialEngine)
    assert engine.select(region_channel(),a).reason=='MONITORING_INTERNAL_SCHOOL_WEEK_NO_PUBLIC_RESULT_2356'


def test_regional_school_week_with_proven_new_public_result_not_blocked():
    a=article('Тиждень початкової школи завершився відкриттям укриття',
              'У школі провели квести та відкрили нове укриття для дітей і вчителів.')
    assert regional_non_news_reason_2356(a)==''


def test_regional_budget_report_not_blanket_blocked_as_brand_pr():
    a=article('Компанія сплатила податки до бюджету громади',
              'До бюджету громади надійшли 12 млн грн податків, які направили на ремонт школи.')
    assert regional_non_news_reason_2356(a)==''
    assert 'не відхиляй' in REGIONAL_NEWS_VALUE_PROMPT_2356


def test_source_quote_repair_preserves_content_and_requires_exact_source():
    a=article('Центр для родин','У Запоріжжі працює ком’юніті-центр «Опліч Хаб», де надають допомогу.')
    raw=('Відкрився ком’юніті-центр «Опліч Хаб, який надає психологічну '
         'підтримку сім’ям у Запоріжжі. Звернутися можуть родини з дітьми. '
         'Кожен відвідувач отримує консультацію за потреби.')
    fixed=source_verified_guillemet_2356(a,raw)
    assert '«Опліч Хаб»' in fixed
    assert fixed.replace('«Опліч Хаб»','«Опліч Хаб')==raw
    assert source_verified_guillemet_2356(article('A','Джерело без такої цитати.'),raw)==raw


def test_repeated_word_outside_quoted_name_is_repaired_but_quoted_words_protected():
    e=ValueError('Жорсткий QA: сусіднє слово повторено двічі')
    raw=('У центрі «Опліч Хаб» відкрили послугу. Фахівці допомагають допомагають '
         'родинам, які звертаються до установи. Допомогу надають людям.')
    fixed=repair_adjacent_repeated_word(raw,e)
    assert fixed and 'допомагають допомагають' not in fixed
    assert not repair_adjacent_repeated_word('Ми чули слова «дуже дуже важко». '+('Це інша історія. '*5),e)
    assert not repair_adjacent_repeated_word(raw,ValueError('AI додав нове число'))


def test_source_floor_remains_owner_500_and_no_replay():
    from telegram_autopilot.v2.monitoring_short_material_2352 import regional_publication_floor_2355
    assert regional_publication_floor_2355(region_channel())==500
    assert regional_publication_floor_2355(creative_channel())==0


def test_corporate_tax_retrospective_without_local_outcome_can_be_skipped():
    a=article('Підприємства металургійної компанії сплатили податки за 9 місяців',
              ('З початку року група підприємств сплатила мільярди гривень податків '
               'до бюджетів усіх рівнів. У компанії наголосили на соціальній '
               'відповідальності та досягненні корпоративних цілей. ' * 6))
    assert regional_non_news_reason_2356(a)=='MONITORING_CORPORATE_AGGREGATE_WITHOUT_LOCAL_RESULT_2356'
    assert hard_editorial_reject(region_channel(),a)=='MONITORING_CORPORATE_AGGREGATE_WITHOUT_LOCAL_RESULT_2356'


def test_local_tax_budget_outcome_stays_publishable():
    a=article('Підприємства компанії сплатили податки за 9 місяців',
              ('Підприємства компанії перерахували кошти: бюджет громади отримав '
               '18 мільйонів гривень на ремонт місцевих лікарень. ' * 6))
    assert regional_non_news_reason_2356(a)==''
