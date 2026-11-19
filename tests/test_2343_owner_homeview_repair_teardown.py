"""Source-only cases for owner CTRL+UA Telegram #2060, LIVE 19 Nov 2026."""
from types import SimpleNamespace
from telegram_autopilot.v2.domain import ChannelMode, DedupeProfile, EditorialRuntimeProfile
from telegram_autopilot.v2.editorial_human_calibration_236 import MARKER
from telegram_autopilot.v2.editorial_owner_2343 import science_procedural_teardown_reason_2343
from telegram_autopilot.v2.editorial_source_topic_2319 import editorial_source_topic_reason_2319

BAD_SOURCE = {
    'title':'How Apple’s HomeView Actively Resists Repairs',
    'raw_text': (
        'How Apple’s HomeView Actively Resists Repairs. '
        'Over the past years there have been hopeful noises about Apple devices becoming easier '
        'to service, but as iFixit found with their teardown things are worse. '
        'The mainboard’s back metal can is glued in place with thermal compound, '
        'speaker connectors disintegrate when you unplug them even after scraping glue. '
        'The display removal is easiest; prying cannot save the speaker modules. '
        'The screws are inaccessible, and the subwoofer is impossible to plug back in. '
        'It may run afoul of right-to-repair regulations or receive a very low score.'
    ),
}
SCIENCE = SimpleNamespace(
    mode=ChannelMode.EDITORIAL,
    editorial_runtime_profile=EditorialRuntimeProfile.STANDARD,
    dedupe_profile=DedupeProfile.SCIENTIFIC_NEWS,
    dedupe_scientific_names=True,
    dedupe_compound_events=True,
    policy=SimpleNamespace(selection_rules=MARKER),
)

def test_live_post_2060_rejected_at_source_selection_and_ready_gate():
    assert science_procedural_teardown_reason_2343(BAD_SOURCE) == 'SCIENCE_TEARDOWN_PROCEDURE_NO_READER_NEWS_2343'
    assert editorial_source_topic_reason_2319(SCIENCE, BAD_SOURCE) == 'SCIENCE_TEARDOWN_PROCEDURE_NO_READER_NEWS_2343'

def test_speculated_right_to_repair_law_is_not_a_confirmed_outcome():
    assert science_procedural_teardown_reason_2343(BAD_SOURCE)

def test_formal_repairability_score_is_not_blocked():
    row = dict(BAD_SOURCE, title='iFixit teardown rates new device repairability score 9/10',
               raw_text=BAD_SOURCE['raw_text']+' iFixit awarded repairability score 9/10.')
    assert science_procedural_teardown_reason_2343(row) == ''

def test_real_hardware_improvement_is_not_blocked():
    row = dict(BAD_SOURCE, title='New modular battery design unveiled in device teardown',
               raw_text=BAD_SOURCE['raw_text']+' A redesigned battery makes replacement possible.')
    assert science_procedural_teardown_reason_2343(row) == ''

def test_enforced_regulator_order_is_not_blocked():
    row = dict(BAD_SOURCE, title='Regulator orders recall after teardown reveals fire risk',
               raw_text=BAD_SOURCE['raw_text']+' A regulator ordered a battery recall.')
    assert science_procedural_teardown_reason_2343(row) == ''

def test_normal_engineering_research_not_blocked():
    row={'title':'New nano-material discovery improves battery efficiency', 'raw_text':BAD_SOURCE['raw_text']}
    assert science_procedural_teardown_reason_2343(row) == ''

def test_unverified_empty_source_not_blocked_by_this_veto():
    assert science_procedural_teardown_reason_2343({'title':BAD_SOURCE['title'],'raw_text':''}) == ''

def test_creative_role_not_targeted():
    channel=SimpleNamespace(mode=ChannelMode.EDITORIAL, editorial_runtime_profile=EditorialRuntimeProfile.COMMERCIAL_EDITORIAL,
        dedupe_profile=DedupeProfile.SCIENTIFIC_NEWS, policy=SimpleNamespace(selection_rules=MARKER))
    assert editorial_source_topic_reason_2319(channel,BAD_SOURCE) != 'SCIENCE_TEARDOWN_PROCEDURE_NO_READER_NEWS_2343'
