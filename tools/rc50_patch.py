from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected exactly one match, found {count}: {old[:100]!r}")
    write(path, text.replace(old, new, 1))


# 1) LanguageTool: RC49 used sub-second liveness probes. On a healthy Windows/JVM
# server that often replies in ~0.4-1.1s, this produced a false-negative loop.
lt_path = "telegram_autopilot/language_tool_local.py"
lt = read(lt_path)
lt = lt.replace('_NEXT_INSTALL_AT = 0.0\n_SHUTDOWN_EVENT = threading.Event()\n', '_NEXT_INSTALL_AT = 0.0\n_SHUTDOWN_EVENT = threading.Event()\n_LT_HEALTH_TIMEOUT = 3.0\n_LT_STARTUP_TIMEOUT = 3.0\n')
for old, new in (
    ('ready = _probe_server(timeout=0.25)', 'ready = _probe_server(timeout=_LT_HEALTH_TIMEOUT)'),
    ('if _probe_server(timeout=0.35):\n        return True\n    root = jar.parent', 'if _probe_server(timeout=_LT_HEALTH_TIMEOUT):\n        return True\n    root = jar.parent'),
    ('if _probe_server(timeout=0.35):\n                _emit(callback, "languagetool", "LanguageTool локальний сервер готовий (127.0.0.1:8081).")', 'if _probe_server(timeout=_LT_STARTUP_TIMEOUT):\n                _emit(callback, "languagetool", "LanguageTool локальний сервер готовий (127.0.0.1:8081).")'),
    ('return _probe_server(timeout=0.7)', 'return _probe_server(timeout=_LT_HEALTH_TIMEOUT)'),
    ('if _probe_server(timeout=0.35):\n        return True\n    if os.environ.get("UA_FREE_DISABLE_LANGUAGETOOL_INSTALL") == "1":', 'if _probe_server(timeout=_LT_HEALTH_TIMEOUT):\n        return True\n    if os.environ.get("UA_FREE_DISABLE_LANGUAGETOOL_INSTALL") == "1":'),
    ('if _probe_server(timeout=0.35):\n            return True\n        try:', 'if _probe_server(timeout=_LT_HEALTH_TIMEOUT):\n            return True\n        try:'),
    ('if _probe_server(timeout=0.2):\n        _NEXT_INSTALL_AT = 0.0', 'if _probe_server(timeout=_LT_HEALTH_TIMEOUT):\n        _NEXT_INSTALL_AT = 0.0'),
    ('value: str, *, timeout: float = 0.75, max_changes: int = 12, require_ready: bool = False', 'value: str, *, timeout: float = 3.0, max_changes: int = 12, require_ready: bool = False'),
    ('if not _probe_server(timeout=min(0.35, max(0.1, float(timeout)))):', 'if not _probe_server(timeout=max(_LT_HEALTH_TIMEOUT, float(timeout))):'),
    ('UAFreeTelegramAutopilot/0.1.0-rc32', 'UAFreeTelegramAutopilot/0.1.0-rc50'),
):
    if old not in lt:
        raise RuntimeError(f"{lt_path}: missing patch target {old!r}")
    lt = lt.replace(old, new)
write(lt_path, lt)

# 2) Article extraction: do not destroy topical advertising/marketing creatives before
# the channel-aware media policy gets a chance to judge them. Unambiguous ad widgets,
# sponsors, affiliates, banners and trackers stay blocked.
extract_path = "telegram_autopilot/article_extractor.py"
extract = read(extract_path)
extract = extract.replace(
    '    "sponsored", "sponsor", "promo", "promotion", "affiliate", "newsletter", "related-content",\n',
    '    "sponsored", "sponsor", "affiliate", "newsletter", "related-content",\n',
)
extract = extract.replace(
    '    "ad", "ads", "advert", "advertising", "banner", "banners", "sponsor", "sponsored", "promo", "promoted",\n    "affiliate", "commercial", "marketing", "recommendations",\n',
    '    "ad", "ads", "advert", "banner", "banners", "sponsor", "sponsored",\n    "affiliate", "recommendations",\n',
)
extract = extract.replace(
    '    "outbrain.com", "taboola.com", "/advertisement/", "/advertising/", "/sponsored/", "/sponsor/",\n    "/affiliate/", "/promo/", "/promos/", "/banner/", "/banners/", "adserver", "ad-server", "adunit",\n',
    '    "outbrain.com", "taboola.com", "/sponsored/", "/sponsor/",\n    "/affiliate/", "/banner/", "/banners/", "adserver", "ad-server", "adunit",\n',
)
write(extract_path, extract)

# 3) Media pipeline: keep strict default anti-ad rules, but make ambiguous thematic
# words channel-aware. Marketing channels may publish the actual campaign creative;
# sponsored widgets, affiliate material, banners, tracking pixels, logos etc. remain blocked.
media_path = "telegram_autopilot/media_pipeline.py"
media = read(media_path)
media = media.replace(
    '_LOGO_WORDS = ("logo", "wordmark", "brandmark", "app-icon", "site-icon", "badge")\n',
    '_MARKETING_CONTEXT_RELAX = {"advertisement", "advertising", "promo", "promotion", "commercial"}\n_LOGO_WORDS = ("logo", "wordmark", "brandmark", "app-icon", "site-icon", "badge")\n',
)
media = media.replace(
    'def _hard_reject(item: PreparedMedia) -> bool:\n    low = (item.url + " " + _candidate_text(item)).casefold().replace("_", "-")\n    if any(term in low for term in _HARD_REJECT):\n        return True\n    if any(term in low for term in _LOGO_WORDS):\n        return True\n    return False\n',
    'def _hard_reject(item: PreparedMedia, *, marketing_context: bool = False) -> bool:\n    low = (item.url + " " + _candidate_text(item)).casefold().replace("_", "-")\n    blocked = _HARD_REJECT\n    if marketing_context:\n        blocked = tuple(term for term in _HARD_REJECT if term not in _MARKETING_CONTEXT_RELAX)\n    if any(term in low for term in blocked):\n        return True\n    if any(term in low for term in _LOGO_WORDS):\n        return True\n    return False\n',
)
media = media.replace(
    'def _score(item: PreparedMedia, *, title: str, article_text: str) -> float:\n    if _hard_reject(item):\n',
    'def _score(item: PreparedMedia, *, title: str, article_text: str, marketing_context: bool = False) -> float:\n    if _hard_reject(item, marketing_context=marketing_context):\n',
)
media = media.replace(
    'def _probe_image(item: PreparedMedia) -> PreparedMedia | None:\n    if _hard_reject(item):\n',
    'def _probe_image(item: PreparedMedia, *, marketing_context: bool = False) -> PreparedMedia | None:\n    if _hard_reject(item, marketing_context=marketing_context):\n',
)
marker = 'def prepare_article_media(layout_json: str, fallback_urls: list[str], *, title: str = "", article_text: str = "") -> PreparedArticleMedia:\n'
if marker not in media:
    raise RuntimeError("media_pipeline.py: prepare_article_media marker not found")
prefix = media.split(marker, 1)[0]
new_prepare = '''def prepare_article_media(\n    layout_json: str,\n    fallback_urls: list[str],\n    *,\n    title: str = "",\n    article_text: str = "",\n    marketing_context: bool = False,\n) -> PreparedArticleMedia:\n    """Validate and rank source media. Media is mandatory at publication time.\n\n    ``marketing_context`` relaxes only ambiguous topical words such as\n    ``advertisement``/``promo``. It never relaxes sponsor/affiliate/banner/tracker\n    or logo/avatar safety rules.\n    """\n    featured, body = _layout_items(layout_json, fallback_urls)\n    if featured and featured.kind == "image":\n        featured.classification = _classify(featured)\n        featured = _probe_image(featured, marketing_context=marketing_context)\n        if featured:\n            featured.relevance_score = _score(\n                featured, title=title, article_text=article_text, marketing_context=marketing_context\n            )\n            semantic_ok = _semantic_media_match(featured, title=title, article_text=article_text)\n            # A validated OG/featured image comes from the article itself. For a\n            # marketing newsroom, generic metadata like "campaign creative" may\n            # contain no title tokens even though the image is the subject of the\n            # story. Keep it, but only after hard-noise and binary image checks.\n            if marketing_context and not semantic_ok:\n                featured.relevance_score = max(40.0, featured.relevance_score)\n                semantic_ok = True\n            if featured.relevance_score < 35 or not semantic_ok:\n                featured = None\n\n    prepared: list[PreparedMedia] = []\n    seen_hashes: set[str] = set()\n    seen_urls: set[str] = set()\n    seen_identities: set[str] = set()\n    for item in body:\n        identity = _media_identity(item.url)\n        if identity in seen_identities or _hard_reject(item, marketing_context=marketing_context):\n            continue\n        item.classification = _classify(item)\n        if item.kind == "image":\n            resolved = _probe_image(item, marketing_context=marketing_context)\n            if not resolved:\n                continue\n            if resolved.digest and resolved.digest in seen_hashes:\n                continue\n            if resolved.url in seen_urls:\n                continue\n            resolved.relevance_score = _score(\n                resolved, title=title, article_text=article_text, marketing_context=marketing_context\n            )\n            semantic_ok = _semantic_media_match(resolved, title=title, article_text=article_text)\n            # For marketing stories an early in-article creative is legitimate even\n            # if its alt text says only "promo"/"campaign". Do not extend this to\n            # late recommendation cards.\n            if marketing_context and not semantic_ok and resolved.position <= 0.20:\n                resolved.relevance_score = max(40.0, resolved.relevance_score)\n                semantic_ok = True\n            if not semantic_ok:\n                continue\n            if resolved.relevance_score < 38:\n                continue\n            if resolved.digest:\n                seen_hashes.add(resolved.digest)\n            seen_urls.add(resolved.url)\n            prepared.append(resolved)\n        else:\n            item.relevance_score = _score(\n                item, title=title, article_text=article_text, marketing_context=marketing_context\n            )\n            video_story = item.kind in {"video", "iframe"} and any(\n                word in (title or "").casefold() for word in _VIDEO_TITLE_WORDS\n            )\n            semantic_ok = _semantic_media_match(item, title=title, article_text=article_text)\n            if marketing_context and item.position <= 0.20:\n                semantic_ok = True\n                item.relevance_score = max(40.0, item.relevance_score)\n            if not video_story and not semantic_ok:\n                continue\n            if item.relevance_score < 38:\n                continue\n            if item.url in seen_urls:\n                continue\n            seen_urls.add(item.url)\n            prepared.append(item)\n        seen_identities.add(identity)\n        if len(prepared) >= 3:\n            break\n    prepared.sort(key=lambda item: (item.position, -item.relevance_score))\n    result = PreparedArticleMedia(featured, prepared)\n    primary_video = result.primary_video\n    if primary_video is not None and primary_video.kind == "iframe":\n        result.video_preview = _youtube_preview(primary_video)\n    return result\n'''
write(media_path, prefix + new_prepare)

# 4) Service: identify marketing channels, require media for every channel, never
# downgrade a failed media post to text-only.
service_path = "telegram_autopilot/service.py"
service = read(service_path)
service = service.replace(
    'from .telegram import TelegramError, build_post_text, send_prepared_photo, send_text, send_video_url\n',
    'from .telegram import TelegramError, build_post_text, send_prepared_photo, send_video_url\n',
)
service = service.replace(
    '\n\nclass AutopilotService:\n',
    '''\n\ndef _marketing_media_context(channel: Channel) -> bool:\n    haystack = f"{channel.name} {channel.editorial_profile}".casefold()\n    return any(token in haystack for token in (\n        "продано", "marketing", "advertis", "реклам", "brand", "бренд", "campaign",\n    ))\n\n\nclass AutopilotService:\n''',
    1,
)
service = service.replace(
    '''                media_urls = self.db.media_urls(row)\n                prepared_media = prepare_article_media(\n                    self.db.article_layout_json(row), media_urls,\n                    title=str(row["title"] or ""), article_text=str(row["raw_text"] or ""),\n                )\n                hero = prepared_media.telegram_hero\n                direct_video = prepared_media.telegram_direct_video\n                video_link = prepared_media.video_link\n                media_present = hero is not None or direct_video is not None\n                telegram_hard_limit = MEDIA_POST_HARD_LIMIT if media_present else TEXT_POST_HARD_LIMIT\n''',
    '''                media_urls = self.db.media_urls(row)\n                marketing_media = _marketing_media_context(channel)\n                prepared_media = prepare_article_media(\n                    self.db.article_layout_json(row), media_urls,\n                    title=str(row["title"] or ""), article_text=str(row["raw_text"] or ""),\n                    marketing_context=marketing_media,\n                )\n                hero = prepared_media.telegram_hero\n                direct_video = prepared_media.telegram_direct_video\n                video_link = prepared_media.video_link\n                media_present = hero is not None or direct_video is not None\n                self._audit(\n                    "media", "ready" if media_present else "rejected",\n                    f"raw={len(media_urls)}; body={len(prepared_media.body)}; featured={bool(prepared_media.featured)}; marketing_context={marketing_media}",\n                    channel_id=channel.id, article_id=article_id,\n                )\n                if not media_present:\n                    reason = "Немає придатного фото/відео: публікація без медіа заборонена для всіх каналів."\n                    self.db.update_article(article_id, status="rejected", reject_reason=reason)\n                    self._audit("media", "required_missing", reason, channel_id=channel.id, article_id=article_id)\n                    continue\n                telegram_hard_limit = MEDIA_POST_HARD_LIMIT\n''',
)
old_fallback = '''                    try:\n                        decision = decide(\n                            channel, row, recent, hard_limit=rewrite_hard_limit, format_marker=format_marker\n                        )\n                    except PostAIQAExhausted as exc:\n                        # Media is optional. If the 900-character caption contract\n                        # is what made otherwise healthy AI candidates fail QA,\n                        # retry the story once as a normal text Telegram post.\n                        # This preserves factual validation while preventing an\n                        # optional image from becoming a publication blocker.\n                        if not media_present or not exc.media_fallback_recommended:\n                            raise\n                        hero = None\n                        direct_video = None\n                        media_present = False\n                        telegram_hard_limit = TEXT_POST_HARD_LIMIT\n                        rewrite_hard_limit = max(300, telegram_hard_limit - len(source_footer) - len(video_footer))\n                        format_marker = f"{POST_FORMAT_PREFIX}{telegram_hard_limit}:{rewrite_hard_limit}:"\n                        self._audit(\n                            "rewrite", "media_to_text_fallback", str(exc)[:1200],\n                            channel_id=channel.id, article_id=article_id,\n                        )\n                        decision = decide(\n                            channel, row, recent, hard_limit=rewrite_hard_limit, format_marker=format_marker\n                        )\n'''
new_fallback = '''                    decision = decide(\n                        channel, row, recent, hard_limit=rewrite_hard_limit, format_marker=format_marker\n                    )\n'''
if old_fallback not in service:
    raise RuntimeError("service.py: media-to-text fallback block not found")
service = service.replace(old_fallback, new_fallback, 1)
old_send = '''                    if direct_video is not None:\n                        result = send_video_url(token, channel.telegram_chat_id, caption, direct_video.url, source_url=source_url)\n                    elif hero is not None:\n                        result = send_prepared_photo(\n                            token, channel.telegram_chat_id, caption,\n                            filename=hero.filename, mime_type=hero.mime_type, data=hero.data, source_url=source_url,\n                        )\n                    else:\n                        result = send_text(token, channel.telegram_chat_id, caption, source_url=source_url)\n                except TelegramError as exc:\n                    if exc.media_rejected:\n                        kind_label = "відео" if direct_video is not None else "фото"\n                        self._emit("warning", f"{channel.name}: Telegram відхилив {kind_label}, публікую цей самий пост без нього")\n                        # If a direct video was rejected but a validated article/YouTube\n                        # preview exists, keep the visual fallback. Otherwise the\n                        # canonical watch link remains in the text.\n                        if direct_video is not None and hero is not None:\n                            try:\n                                result = send_prepared_photo(\n                                    token, channel.telegram_chat_id, caption,\n                                    filename=hero.filename, mime_type=hero.mime_type, data=hero.data, source_url=source_url,\n                                )\n                            except TelegramError as photo_exc:\n                                if not photo_exc.media_rejected:\n                                    raise\n                                result = send_text(token, channel.telegram_chat_id, caption, source_url=source_url)\n                        else:\n                            result = send_text(token, channel.telegram_chat_id, caption, source_url=source_url)\n                    else:\n                        raise\n'''
new_send = '''                    if direct_video is not None:\n                        result = send_video_url(token, channel.telegram_chat_id, caption, direct_video.url, source_url=source_url)\n                    elif hero is not None:\n                        result = send_prepared_photo(\n                            token, channel.telegram_chat_id, caption,\n                            filename=hero.filename, mime_type=hero.mime_type, data=hero.data, source_url=source_url,\n                        )\n                    else:\n                        raise RuntimeError("Mandatory media disappeared after the media gate")\n                except TelegramError as exc:\n                    if exc.media_rejected and direct_video is not None and hero is not None:\n                        self._emit("warning", f"{channel.name}: Telegram відхилив відео, пробую перевірене фото")\n                        result = send_prepared_photo(\n                            token, channel.telegram_chat_id, caption,\n                            filename=hero.filename, mime_type=hero.mime_type, data=hero.data, source_url=source_url,\n                        )\n                    else:\n                        raise\n'''
if old_send not in service:
    raise RuntimeError("service.py: Telegram media fallback block not found")
service = service.replace(old_send, new_send, 1)
write(service_path, service)

# 5) Version and release metadata.
write("VERSION.txt", "0.1.0-rc50\n")
write("PUBLIC_VERSION.txt", "0.1.0-rc50\n")
replace_once("telegram_autopilot/__init__.py", '__version__ = "0.1.0-rc49"', '__version__ = "0.1.0-rc50"')

changelog = read("CHANGELOG.md")
entry = '''# Changelog\n\n## 0.1.0-rc50 — 2026-08-28\n\n### Fixed\n- LanguageTool Windows health checks now allow real JVM response time instead of falsely declaring a healthy local server dead after 0.2-0.35 seconds.\n- Marketing-channel media extraction no longer discards legitimate campaign creatives merely because metadata contains advertising/marketing/promo vocabulary.\n- Channel-aware media filtering keeps sponsor/affiliate/banner/tracker/logo/avatar rejection strict while allowing topical advertising creatives for marketing channels.\n- Media is mandatory for every Telegram channel. Missing or Telegram-rejected media never falls back to a text-only publication.\n- Added media-stage audit counters so a no-media rejection records raw candidate count and prepared result count.\n\n### Preserved\n- RC49 simplified human-readable editorial pipeline and Editorial Learning Loop.\n- Existing Data, channels, sources, Telegram credentials, publication history and editorial memory remain compatible.\n\n'''
if changelog.startswith("# Changelog\n"):
    changelog = entry + changelog[len("# Changelog\n\n"):]
else:
    changelog = entry + changelog
write("CHANGELOG.md", changelog)

write("RELEASE_NOTES_v0.1.0-rc50.md", '''# UA FREE Telegram Autopilot v0.1.0-rc50\n\n## Main fixes\n- Fixes the false LanguageTool unavailable/retry loop on Windows by using realistic local-server health timeouts.\n- Restores media throughput for marketing channels such as ПРОДАНО! without weakening the anti-banner/affiliate/sponsor protections.\n- Advertising, campaign and promo vocabulary can describe the actual editorial subject in a marketing channel and is no longer automatically treated as junk media.\n- Every channel remains media-only: no photo/video means no Telegram publication, and a rejected media upload does not downgrade to text-only.\n- Media audit entries now expose raw/prepared candidate counts for diagnosis.\n\n## Compatibility\nCopy the complete existing `Data` directory into the new portable folder. Existing channels, sources, tokens, history and Editorial Memory are preserved.\n''')

# 6) Regression tests for the exact RC50 failures.
write("tests/test_rc50_media_languagetool.py", '''from __future__ import annotations\n\nfrom types import SimpleNamespace\nfrom pathlib import Path\n\nimport telegram_autopilot.language_tool_local as lt\nfrom telegram_autopilot.article_extractor import editorial_media_candidate\nfrom telegram_autopilot.media_pipeline import PreparedMedia, _hard_reject\nfrom telegram_autopilot.service import _marketing_media_context\n\n\ndef test_languagetool_operator_status_uses_realistic_health_timeout(monkeypatch):\n    calls = []\n    monkeypatch.setattr(lt, "_probe_server", lambda *, timeout: calls.append(timeout) or False)\n    monkeypatch.setattr(lt, "_find_server_jar", lambda: None)\n    monkeypatch.setattr(lt, "_read_stats", lambda: {})\n    lt.languagetool_status()\n    assert calls and calls[0] >= 3.0\n\n\ndef test_marketing_context_does_not_treat_campaign_vocabulary_as_junk():\n    item = PreparedMedia(1, "image", "https://example.com/advertisement/promo-campaign.jpg", context="marketing promotion creative")\n    assert _hard_reject(item)\n    assert not _hard_reject(item, marketing_context=True)\n\n\ndef test_marketing_context_still_rejects_sponsored_banner_noise():\n    item = PreparedMedia(1, "image", "https://example.com/sponsored/banner.jpg", context="affiliate sponsored banner")\n    assert _hard_reject(item, marketing_context=True)\n\n\ndef test_extractor_defers_topical_promo_words_to_channel_policy():\n    url = editorial_media_candidate(\n        "https://example.com/story", "/advertising/promo-campaign.jpg",\n        context="marketing promotion campaign creative", width=1200, height=800,\n    )\n    assert url.endswith("/advertising/promo-campaign.jpg")\n\n\ndef test_extractor_keeps_unambiguous_sponsored_noise_blocked():\n    assert not editorial_media_candidate(\n        "https://example.com/story", "/sponsored/banner.jpg",\n        context="sponsored affiliate banner", width=1200, height=800,\n    )\n\n\ndef test_prodano_is_detected_as_marketing_media_context():\n    channel = SimpleNamespace(name="ПРОДАНО!", editorial_profile="Реклама, бренди і все, що продає увагу")\n    assert _marketing_media_context(channel)\n\n\ndef test_service_has_no_text_only_telegram_fallback():\n    source = (Path(__file__).resolve().parents[1] / "telegram_autopilot" / "service.py").read_text(encoding="utf-8")\n    assert "send_text(" not in source\n    assert "публікація без медіа заборонена для всіх каналів" in source\n''')

# Remove the one-shot patch machinery from the resulting branch commit.
for rel in ("tools/rc50_patch.py", ".github/workflows/rc50-patch.yml"):
    try:
        (ROOT / rel).unlink()
    except FileNotFoundError:
        pass
