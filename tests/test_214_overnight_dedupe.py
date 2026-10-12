"""Night-run 2.1.4 regression: unrelated CTRL+UA stories must not merge."""
from telegram_autopilot.v2.event_dedupe_guard import event_fingerprint_same_event
from telegram_autopilot.v2.storage import V2Store

def row(title,text,source):
    return {"title":title,"raw_text":text,"event_summary":"","final_text":"",
            "source_id":source,"source_name":"Tech news","source_url":"https://example.com/"+str(source),
            "canonical_source_url":"https://example.com/"+str(source),"content_hash":""}

FOOTER=("Facebook Twitter LinkedIn Reddit Flipboard Email Read more "
        "Related posts Subscribe Newsletter Privacy Share technology ")*15

def test_citroen_ev_not_3d_printed_jet_aircraft():
    a=row("Adorable retro EV concept takes the battle to cheap Chinese rivals",FOOTER+"Citroen 2CV concept car",1)
    b=row("World's first 3D-printed remote control aircraft with a jet turbine takes flight",FOOTER+"jet turbine aircraft",2)
    assert not event_fingerprint_same_event(a,b,rare_terms=True,compound_events=True)[0]

def test_microsoft_memory_cleanup_not_meta_agent_reasoning():
    a=row("Clearing chat history helps AI agents find better solutions",FOOTER+"Microsoft context clearing experiment",1)
    b=row("Why giving AI agents more compute isn't enough and what Meta proposes instead",FOOTER+"Meta agent orchestration research",2)
    assert not event_fingerprint_same_event(a,b,rare_terms=True,compound_events=True)[0]

def test_exact_same_url_stays_duplicate():
    a=row("Different headline one","a",1)
    b=row("Different headline two","b",2)
    b["canonical_source_url"]=a["canonical_source_url"]
    assert event_fingerprint_same_event(a,b)[0]
