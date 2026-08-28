from pathlib import Path

root = Path(__file__).resolve().parents[1]
media = root / "telegram_autopilot" / "media_pipeline.py"
text = media.read_text(encoding="utf-8")
old = '    "advertisement", "advertorial", "sponsored", "sponsor", "affiliate", "promo", "promotion",\n'
new = '    "advertisement", "advertising", "advertorial", "sponsored", "sponsor", "affiliate", "promo", "promotion", "commercial",\n'
if text.count(old) != 1:
    raise RuntimeError(f"media hard-reject target count={text.count(old)}")
media.write_text(text.replace(old, new, 1), encoding="utf-8")

test = root / "tests" / "test_rc50_media_languagetool.py"
t = test.read_text(encoding="utf-8")
needle = '''def test_marketing_context_still_rejects_sponsored_banner_noise():\n    item = PreparedMedia(1, "image", "https://example.com/sponsored/banner.jpg", context="affiliate sponsored banner")\n    assert _hard_reject(item, marketing_context=True)\n\n\n'''
addition = needle + '''def test_default_context_still_rejects_advertising_commercial_metadata():\n    item = PreparedMedia(1, "image", "https://example.com/campaign.jpg", context="advertising commercial creative")\n    assert _hard_reject(item)\n    assert not _hard_reject(item, marketing_context=True)\n\n\n'''
if t.count(needle) != 1:
    raise RuntimeError(f"test insertion target count={t.count(needle)}")
test.write_text(t.replace(needle, addition, 1), encoding="utf-8")

for rel in ("tools/rc50_patch.py", ".github/workflows/rc50-patch.yml"):
    try:
        (root / rel).unlink()
    except FileNotFoundError:
        pass
