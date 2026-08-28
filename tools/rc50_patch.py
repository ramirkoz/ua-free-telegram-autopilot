from pathlib import Path

root = Path(__file__).resolve().parents[1]
article = root / "telegram_autopilot" / "article_extractor.py"
text = article.read_text(encoding="utf-8")
old = '    "cocoon ai summary", "ai-summary", "ai_summary", "ai summary", "advertisement", "advertorial",\n'
new = '    "cocoon ai summary", "ai-summary", "ai_summary", "ai summary", "advertorial",\n'
if text.count(old) != 1:
    raise RuntimeError(f"article_extractor target count={text.count(old)}")
article.write_text(text.replace(old, new, 1), encoding="utf-8")

test = root / "tests" / "test_rc50_media_languagetool.py"
t = test.read_text(encoding="utf-8")
old_test = '        context="marketing promotion campaign creative", width=1200, height=800,\n'
new_test = '        context="marketing advertisement promotion campaign creative", width=1200, height=800,\n'
if t.count(old_test) != 1:
    raise RuntimeError(f"test target count={t.count(old_test)}")
test.write_text(t.replace(old_test, new_test, 1), encoding="utf-8")

for rel in ("tools/rc50_patch.py", ".github/workflows/rc50-patch.yml"):
    try:
        (root / rel).unlink()
    except FileNotFoundError:
        pass
