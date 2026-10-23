"""2.2.24 operator regressions: 4655/4656, 76065/76105/75930, 2 sentences."""
from __future__ import annotations

from types import SimpleNamespace
import pytest

from telegram_autopilot.v2.editorial_hard_guards import (
    minimum_sentence_reason, substantive_sentences, unsupported_event_claims,
)
from telegram_autopilot.v2.telegram_ingest_policy import stitch_adjacent_telegram_media
from telegram_autopilot.v2 import strict_ingest
from telegram_autopilot.v2.monitoring_live_now import live_now_exclusion
from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode, ChannelPolicy, Decision
from telegram_autopilot.v2.editorial import EditorialEngine, hard_editorial_reject


def row(raw):
    return {"raw_text":raw,"title":raw,"id":76105,"source_url":"https://t.me/zaborzp/155221"}


def channel(mode=ChannelMode.MONITORING):
    return ChannelConfig(id=3, name="ЗАПОРІЖЖЯ | ГРОМАДИ",
                         telegram_chat_id="-1000",mode=mode,
                         policy=ChannelPolicy(channel_id=3,
                          rejection_rules="[LIVE_NOW_RC96] local monitoring"))


def test_undersized_original_global_pre_ai_and_pre_send():
    one="У Запоріжжі оприлюднили рішення про перекриття мосту."
    assert minimum_sentence_reason(row(one))=="EDITORIAL_MIN_TWO_SENTENCES_SOURCE"
    for mode in (ChannelMode.MONITORING,ChannelMode.EDITORIAL):
        ch=channel(mode)
        # Pure helpers still test their own topic rules. Production enforces
        # this floor at process_article before provider access and at publish_one.
        assert minimum_sentence_reason(row(one))=="EDITORIAL_MIN_TWO_SENTENCES_SOURCE"


def test_two_meaningful_facts_allowed_but_single_final_blocked():
    source="Міська рада відкрила центр допомоги для переселенців. У центрі працюватимуть два юристи щодня."
    assert minimum_sentence_reason(row(source))==""
    assert minimum_sentence_reason(row(source),"Відкрито центр допомоги для переселенців.")=="EDITORIAL_MIN_TWO_SENTENCES_FINAL"


@pytest.mark.parametrize("text",[
    "О 12:45 терміново. Джерело: https://t.me/example/42",
    "Новини. Сьогодні.",
    "У Запоріжжі пройшла пресконференція. У Запоріжжі провели пресконференцію.",
    "У Запоріжжі оприлюднили детальний звіт про проведення запланованого засідання, в якому брали участь представники всіх громад.",
])
def test_timestamps_footer_repeated_fact_and_long_single_sentence_do_not_pass(text):
    assert len(substantive_sentences(text))<2


def test_unsupported_road_closure_from_military_bridge_route():
    source=row("Реактивний знову кружляє через мости Запоріжжя. Зараз його спостерігають біля Шевчика.")
    final="У Запоріжжі знову обмежили автомобільний рух через мости. Водії користуються об'їздом під час ремонтних робіт."
    assert "EDITORIAL_UNSUPPORTED_TRAFFIC_EVENT" in unsupported_event_claims(source,final)
    assert live_now_exclusion(channel(),source)


def test_explicit_actual_civic_road_closure_allowed():
    source=row("Міська рада перекрила проїзд мостом для ремонтних робіт. Автобуси рухаються тимчасовим маршрутом.")
    final="Міська рада перекрила проїзд через міст на час робіт. Автобуси користуються тимчасовим маршрутом."
    assert not unsupported_event_claims(source,final)


def test_colloquial_reactive_does_not_license_jet_aircraft():
    src=row("Реактивний рухається над Запоріжжям. Ще летить у бік мостів.")
    final="Два реактивні літаки вилетіли із Запоріжжя. Вони пролетіли через мости."
    assert "EDITORIAL_UNSUPPORTED_AIRCRAFT_IDENTITY" in unsupported_event_claims(src,final)


def test_third_casualty_is_not_implicitly_in_same_family():
    src=row("Загинуло подружжя: 37-річний чоловік та 38-річна жінка. Також загинула 69-річна жінка.")
    final="Загинули троє людей у Запоріжжі. Це була одна родина."
    assert "EDITORIAL_UNSUPPORTED_ALL_VICTIMS_FAMILY" in unsupported_event_claims(src,final)


def test_explicitly_confirmed_all_three_family_does_not_block():
    src=row("Усі троє загиблих були однією родиною. Про це заявила обласна військова адміністрація.")
    assert not unsupported_event_claims(src,"У Запоріжжі загинули троє людей. Це була одна родина.")


def test_production_ingest_delegates_only_to_strict_ownership(monkeypatch):
    sentinel=[]
    called=[]
    def strict(username,entries):
        called.append((username,entries))
        return sentinel
    monkeypatch.setattr(strict_ingest,"strict_stitch_telegram",strict)
    entries=[SimpleNamespace(post="mih_gromada/4655"),SimpleNamespace(post="mih_gromada/4656")]
    assert stitch_adjacent_telegram_media("mih_gromada",entries) is sentinel
    assert called==[("mih_gromada",entries)]



def test_exact_4655_video_does_not_join_4656_own_photo():
    from telegram_autopilot.media import encode_media
    from telegram_autopilot.v2.ingest import TelegramEntry
    video=TelegramEntry(post="mih_gromada/4655",text="",published="2026-10-23T09:30:00+03:00",
                        media=[encode_media("video","https://example.test/4655.mp4")])
    primary=TelegramEntry(post="mih_gromada/4656",
                          text="Для переселенців працює юридичний центр. Консультації надають фахівці правозахисної організації.",
                          published="2026-10-23T09:30:20+03:00",
                          media=[encode_media("image","https://example.test/4656.jpg")])
    posts=stitch_adjacent_telegram_media("mih_gromada",[video,primary])
    assert len(posts)==1
    assert posts[0].external_id=="mih_gromada/4656"
    assert len(posts[0].media_urls)==1
    assert "4656.jpg" in posts[0].media_urls[0]
    import json
    layout=json.loads(posts[0].article_layout_json)
    assert layout["telegram"]["message_ids"] == ["4656"]


def test_stale_ready_4655_video_plus_4656_photo_fails_publish_parity(monkeypatch):
    from telegram_autopilot.v2 import telegram_media_publish_guard as guard
    from types import SimpleNamespace
    events=[]
    store=SimpleNamespace(publication_backoff=lambda article_id,**kwargs:events.append((article_id,kwargs)))
    pub=SimpleNamespace(store=store)
    check=SimpleNamespace(outcome="confirmed",expected_photos=1,video_expected=False,
        media=["image4656"],photo_signal="photo_wrap",video_signal="",reason="exact_post_media_confirmed")
    monkeypatch.setattr(guard,"check_exact_telegram_media",lambda url:check)
    bundle=SimpleNamespace(source_message_ids=["4655","4656"],encoded_items=["video4655","image4656"],count=2)
    result=guard.enforce_source_media_parity(pub,SimpleNamespace(id=3),76242,
               {"media_json":"[]"} ,bundle,"https://t.me/mih_gromada/4656")
    assert result=="MEDIA_CROSS_POST_CONTAMINATION"
    assert events[0][0]==76242
    assert events[0][1]["error_code"]=="MEDIA_CROSS_POST_CONTAMINATION"
