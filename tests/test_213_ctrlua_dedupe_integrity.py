"""CTRL+UA 2.1.3: no cross-story dedupe from page boilerplate."""
from telegram_autopilot.v2.event_dedupe_guard import event_fingerprint_same_event

def record(title, text, source_id, url):
    return {
        "title": title, "raw_text": text, "final_text": "",
        "event_summary": "", "source_id": source_id, "source_url": url,
        "canonical_source_url": url, "content_hash": "", "source_name": "Technology News",
    }

TEMPLATE = ("Email Share Facebook Flipboard Subscribe Radar Curated OpenAI "
            "Discover news October Privacy Read more Authors Technology ") * 8

def test_microsoft_maia_not_openai_model_self_destruction():
    left = record("Microsoft scales Maia chips to gigawatt data centers", TEMPLATE + "Microsoft Maia infrastructure chips", 11, "https://news.example/maia")
    right = record("OpenAI model destroys its own working environment", TEMPLATE + "AI model self destructive experiment", 22, "https://other.example/model")
    yes, reason = event_fingerprint_same_event(left, right, rare_terms=True, compound_events=True)
    assert not yes, reason

def test_iphone_accessory_not_ugreen_charger_discount():
    left = record("Best accessories for the iPhone Duo", TEMPLATE + "iPhone Duo cases and attachments", 11, "https://news.example/duo")
    right = record("Ugreen charger deal drops in price", TEMPLATE + "Ugreen discount deal for charging brick", 22, "https://other.example/ugreen")
    yes, reason = event_fingerprint_same_event(left, right, rare_terms=True, compound_events=True)
    assert not yes, reason

def test_exact_source_url_still_blocks_repeat():
    left = record("New AI research announced by Microsoft", "summary", 11, "https://news.example/post?a=1")
    right = record("Completely different teaser heading", "summary", 22, "https://news.example/post?a=1")
    yes, reason = event_fingerprint_same_event(left, right)
    assert yes, reason

def test_identical_content_hash_still_blocks_repeat():
    left = record("New product news", "a", 11, "https://news.example/one")
    right = record("Other heading", "a", 22, "https://other.example/two")
    left["content_hash"] = right["content_hash"] = "verified-article-body"
    yes, reason = event_fingerprint_same_event(left, right)
    assert yes, reason
