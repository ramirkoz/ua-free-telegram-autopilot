"""Real-world shape: two publishers report the same refrigeration incident differently.

All story text is test data; no named brands, publishers or channels are used
as production routing rules.
"""
from telegram_autopilot.v2.event_dedupe_guard import event_fingerprint_same_event


def story(title, body, source_id):
    return {
        "title": title, "raw_text": body, "source_id": source_id,
        "source_url": "https://independent.example/" + str(source_id),
    }


def test_differently_scoped_incident_headlines_match_with_corrobating_facts():
    first = story(
        "Cyberattacks crank French supermarket refrigeration systems to 50C",
        "Carrefour, Monoprix and Danfoss reported hackers breached cooling controllers. "
        "Temperatures increased to 50 degrees, spoiled food and forced supermarkets "
        "to discard products. Danfoss acknowledged outdated firmware allowed attackers "
        "to change controller settings remotely in stores across France.",
        11,
    )
    second = story(
        "Europe supermarket fridges defrosted after hackers change thermostats",
        "Danfoss cooling control systems were hacked, including stores operated by "
        "Carrefour and Monoprix. Attackers changed refrigeration settings over the "
        "internet, increasing temperature to 50 degrees. The food spoiled and the "
        "retail chains discarded their products. Old controller firmware was involved.",
        19,
    )
    same, reason = event_fingerprint_same_event(first, second)
    assert same, reason


def test_two_companies_in_different_events_not_duplicate_despite_same_temperature():
    first = story(
        "Carrefour and Danfoss refrigeration hack in France",
        "Carrefour and Danfoss discovered a hack of refrigeration equipment. The "
        "attackers changed controller temperature to 50 and spoiled food. "
        "Retail staff discarded products because of hacked outdated firmware.",
        11,
    )
    second = story(
        "Danfoss and Carrefour open solar research trial",
        "Danfoss and Carrefour announced a solar research trial in Spain. The "
        "company published measurements of 50 kilowatts from photovoltaic panels. "
        "The project invested in sustainable electricity and storage technology.",
        19,
    )
    same, _ = event_fingerprint_same_event(first, second)
    assert not same


def test_unrelated_incidents_with_same_actor_and_number_not_merged():
    first = story(
        "Danfoss and Carrefour cooling controls hacked",
        "Danfoss and Carrefour say hackers breached cooling controllers. "
        "Supermarkets lost food when the temperature reached 50 degrees. "
        "Old firmware enabled remote access to equipment.",
        11,
    )
    second = story(
        "Danfoss and Carrefour warehouse ransomware incident",
        "Danfoss and Carrefour experienced a separate hack at their warehouse. "
        "Attackers stole 50 documents and demanded ransom from IT servers. "
        "No refrigeration equipment or store temperatures were affected.",
        19,
    )
    same, _ = event_fingerprint_same_event(first, second)
    assert not same
