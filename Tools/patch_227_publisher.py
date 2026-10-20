"""One-time branch publisher hook for 2.2.7; fail if source markers drift."""
from pathlib import Path

path = Path("telegram_autopilot/v2/publisher.py")
source = path.read_text(encoding="utf-8")
start_marker = "        # 2.2.6 P0: an empty Telegram bundle is not proof"
end_marker = "        # RC56: if the story is actually about a video"
assert start_marker in source and end_marker in source
start = source.index(start_marker)
end = source.index(end_marker, start)
replacement = '''        # 2.2.7: exact-source photo/album/video parity before any delivery.
        if bundle.source_kind == "telegram":
            from .telegram_media_publish_guard import enforce_source_media_parity
            verified = enforce_source_media_parity(
                self, channel, article_id, article, bundle, source_url)
            if isinstance(verified, str):
                return verified
            article, bundle = verified

'''
path.write_text(source[:start] + replacement + source[end:], encoding="utf-8")

for filename in ("VERSION.txt", "PUBLIC_VERSION.txt", "V2_VERSION.txt"):
    Path(filename).write_text("2.2.7\n", encoding="utf-8")

pkg = Path("telegram_autopilot/__init__.py")
original = pkg.read_text(encoding="utf-8")
assert '__version__ = "2.2.6"' in original
pkg.write_text(original.replace('__version__ = "2.2.6"', '__version__ = "2.2.7"'), encoding="utf-8")
pkg = Path("pyproject.toml")
original = pkg.read_text(encoding="utf-8")
assert 'version = "2.2.6"' in original
pkg.write_text(original.replace('version = "2.2.6"', 'version = "2.2.7"'), encoding="utf-8")
print("AUTOPILOT_227_PUBLISHER_HOOK_AND_VERSION_READY")
