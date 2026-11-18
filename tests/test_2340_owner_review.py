"""Actual owner-reviewed 18 Nov 2026 v2.3.39 regressions; no Telegram sends."""
from types import SimpleNamespace

from telegram_autopilot.v2.editorial_live_2340 import same_science_milestone_without_new_facts
from telegram_autopilot.v2.dedupe import _same_event
from telegram_autopilot.v2.domain import ChannelMode
from telegram_autopilot.v2.media_pipeline import MediaBundle, MediaItem, single_captioned_album_2340
from telegram_autopilot.v2.monitoring_source_scope_2317 import monitoring_source_scope_reason_2317


VOYAGER = dict(source_id=74,
    title='Voyager 1 is one light-day away from Earth, according to NASA estimate',
    raw_text='NASA estimates Voyager 1 is a light-day away. Radio signals take 24 hours.')
VOYAGER_AGAIN = dict(source_id=62,
    title='Voyager 1 Beat the Odds and Is Still Working a Light-Day Away From Earth',
    raw_text='Voyager 1 continues to send scientific information after nearly 50 years.')
GOLDEN_RECORD = dict(source_id=59,
    title="Voyager 1 at one light-day: Historian revisits Golden Record's forgotten details",
    raw_text='Historian Glen Swanson discovered a second set of Golden Record instructions.')


def test_voyager_original_cross_source_is_same_milestone():
    assert same_science_milestone_without_new_facts(VOYAGER_AGAIN, VOYAGER)
    assert _same_event(VOYAGER_AGAIN, VOYAGER)[0]


def test_voyager_golden_record_remains_a_distinct_discovery():
    assert not same_science_milestone_without_new_facts(GOLDEN_RECORD, VOYAGER)
    assert not _same_event(GOLDEN_RECORD, VOYAGER)[0]


def test_nasa_confirmation_is_not_suppressed():
    confirmed = dict(VOYAGER_AGAIN, title='NASA confirms Voyager 1 is one light-day away from Earth')
    assert not same_science_milestone_without_new_facts(confirmed, VOYAGER)


def _monitor():
    return SimpleNamespace(mode=ChannelMode.MONITORING,
                           policy=SimpleNamespace(rejection_rules='[LIVE_NOW_RC96]'))


def test_poland_foreign_security_story_rejected_as_nonlocal():
    article = dict(title='росіяни планували провести операцію в Польщі під чужим прапором',
                   raw_text='Спецслужби планували диверсію на території Польщі.')
    assert monitoring_source_scope_reason_2317(_monitor(), article) == 'MONITORING_UNRELATED_FOREIGN_SECURITY_2340'


def test_british_national_military_aid_rejected_as_nonlocal():
    article = dict(title='Велика Британія передасть Україні понад 1000 ракет ППО та радари',
                   raw_text='Велика Британія оголосила пакет допомоги на £240 млн.')
    assert monitoring_source_scope_reason_2317(_monitor(), article) == 'MONITORING_NONLOCAL_FOREIGN_MILITARY_AID_2340'


def test_direct_local_military_impact_not_auto_blocked():
    article = dict(title='Запоріжжя отримало радари ППО',
                   raw_text='Велика Британія передала обладнання для захисту Запоріжжя.')
    assert not monitoring_source_scope_reason_2317(_monitor(), article)


def test_national_idp_service_still_eligible():
    article = dict(title='Дія: національне оформлення виплат ВПО',
                   raw_text='Нові правила допомоги для переселенців діятимуть по всій Україні.')
    assert not monitoring_source_scope_reason_2317(_monitor(), article)


def test_single_captioned_album_max_ten_assets_in_source_order():
    images = tuple(MediaItem('image', f'https://example.org/story/img-{i}.jpg') for i in range(16))
    raw = MediaBundle(items=images, source_kind='rss', source_media_count=16,
                      gallery_items_found=16, gallery_items_kept=16)
    capped = single_captioned_album_2340(raw)
    assert capped.items == images[:10]
    assert capped.source_media_count == 10
    assert capped.gallery_items_kept == 10
    assert dict(capped.drop_reasons)['single_captioned_album_limit_2340'] == 6
    assert single_captioned_album_2340(capped) is capped
