from telegram_autopilot.v2.event_dedupe_guard import event_fingerprint_same_event


def story(title, body, source_id):
    return {"title": title, "raw_text": body, "source_id": source_id,
            "source_url": "https://example.com/" + str(source_id)}


def test_same_brand_object_and_multiple_facts_from_independent_sources():
    common = ("Chipotle unveiled an oversized carry bag for large group dining orders. "
              "The unusual giant bag holds multiple family meals and bundled takeaway food. "
              "The campaign shows friends ordering together and sharing dinner. ")
    one = story("Chipotle drops a giant bag for group dining", common + "A promotional demonstration reveals the product.", 1)
    two = story("Chipotle oversized bag carries food for family", common + "The giant bag design makes group orders easier.", 2)
    same, why = event_fingerprint_same_event(one, two, commercial_profile=True)
    assert same, why


def test_same_brand_different_product_not_duplicate():
    one = story("Chipotle launches giant carry bag", "A giant bag transports dinner for groups at home. " * 5, 1)
    two = story("Chipotle launches new spicy drink", "A new beverage is served at stores with summer promotions. " * 5, 2)
    same, _ = event_fingerprint_same_event(one, two, commercial_profile=True)
    assert not same


def test_shared_brand_and_boilerplate_not_sufficient():
    common = "Subscribe to the newsletter and follow us for marketing brand stories about Chipotle. "
    one = story("Chipotle giant bag for families", common * 8 + "oversized carry container", 1)
    two = story("Chipotle new family menu promotion", common * 8 + "limited menu rewards", 2)
    same, _ = event_fingerprint_same_event(one, two, commercial_profile=True)
    assert not same
