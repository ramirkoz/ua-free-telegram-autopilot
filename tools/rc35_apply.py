from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, got {count}")
    return text.replace(old, new, 1)


# 1) Domain: explicit, per-channel attribution mode.
path = "telegram_autopilot/v2/domain.py"
text = read(path)
text = replace_once(
    text,
    'class ChannelMode(StrEnum):\n    EDITORIAL = "editorial"\n    MONITORING = "monitoring"\n\n\nclass Stage(StrEnum):',
    'class ChannelMode(StrEnum):\n    EDITORIAL = "editorial"\n    MONITORING = "monitoring"\n\n\nclass SourceAttributionMode(StrEnum):\n    STANDARD = "standard"\n    NAMED_SOURCE = "named_source"\n\n\nclass Stage(StrEnum):',
    "domain enum",
)
text = replace_once(
    text,
    '    include_source_link: bool = True\n    source_link_required: bool = True\n    poll_interval_minutes: int = 5',
    '    include_source_link: bool = True\n    source_link_required: bool = True\n    source_attribution_mode: SourceAttributionMode = SourceAttributionMode.STANDARD\n    poll_interval_minutes: int = 5',
    "domain field",
)
write(path, text)


# 2) Generic source attribution module. Runtime behavior is driven ONLY by the explicit channel setting.
write(
    "telegram_autopilot/v2/source_attribution.py",
    '''from __future__ import annotations

from typing import Any, Mapping

from .domain import ChannelConfig, SourceAttributionMode


def _value(row: Mapping[str, Any] | Any, key: str, default: Any = "") -> Any:
    try:
        value = row[key]
    except Exception:
        value = getattr(row, key, default)
    return default if value is None else value


def clean_source_name(value: Any, limit: int = 120) -> str:
    """Return the operator-configured source name in a footer/prompt-safe form."""
    return " ".join(str(value or "").split()).strip()[: max(1, int(limit))]


def named_source_enabled(channel: ChannelConfig) -> bool:
    """Use named attribution only when the operator explicitly enabled it for this channel."""
    try:
        return SourceAttributionMode(str(channel.source_attribution_mode)) == SourceAttributionMode.NAMED_SOURCE
    except Exception:
        return False


def source_context_name(channel: ChannelConfig, article: Mapping[str, Any] | Any) -> str:
    """Return the configured donor/source name only for explicit named-source mode."""
    if not named_source_enabled(channel):
        return ""
    return clean_source_name(_value(article, "source_name", ""))


def source_footer_label(channel: ChannelConfig, article: Mapping[str, Any] | Any) -> str:
    name = source_context_name(channel, article)
    return f"Читати у «{name}»" if name else ""


def source_body_hard_limit(
    channel: ChannelConfig,
    article: Mapping[str, Any] | Any,
    *,
    telegram_limit: int = 900,
    default_body_limit: int = 880,
) -> int:
    """Reserve caption space for a custom named-source footer when enabled."""
    footer = source_footer_label(channel, article)
    if not footer:
        return int(default_body_limit)
    available = int(telegram_limit) - len(footer) - 2
    return max(200, min(int(default_body_limit), available))


def require_source_context(text: str, source_name: str) -> None:
    """Keep the explicitly configured source context in the final rewrite."""
    name = clean_source_name(source_name)
    if not name:
        return
    if name.casefold() not in str(text or "").casefold():
        raise ValueError(f"У рерайті втрачено назву джерела: {name}")


def attribution_for_article(
    channel: ChannelConfig,
    article: Mapping[str, Any] | Any,
    *,
    source_url: str,
    source_urls: list[str] | tuple[str, ...],
) -> tuple[list[str], list[str] | None]:
    """Return footer URLs/labels without changing reader-action links in the body.

    ``named_source`` uses the exact primary original-post URL and the configured source
    name. ``standard`` keeps the historical ``Джерело`` / ``Джерело N`` contract.
    """
    label = source_footer_label(channel, article)
    if label and str(source_url or "").startswith(("http://", "https://")):
        return [str(source_url)], [label]
    return list(source_urls), None
''',
)

# Keep the RC34 module import-safe for old imports/tests, but remove all name-based runtime detection.
write(
    "telegram_autopilot/v2/community_context.py",
    '''"""Compatibility aliases for RC34 imports.

Named attribution is generic since RC35 and is controlled by an explicit channel setting.
There is intentionally no runtime detection based on the channel name.
"""

from .source_attribution import (
    attribution_for_article,
    clean_source_name,
    named_source_enabled,
    require_source_context,
    source_body_hard_limit,
    source_context_name,
    source_footer_label,
)

community_source_name = source_context_name
community_footer_label = source_footer_label
community_body_hard_limit = source_body_hard_limit
require_community_context = require_source_context

__all__ = [
    "attribution_for_article",
    "clean_source_name",
    "named_source_enabled",
    "require_source_context",
    "source_body_hard_limit",
    "source_context_name",
    "source_footer_label",
    "community_source_name",
    "community_footer_label",
    "community_body_hard_limit",
    "require_community_context",
]
''',
)


# 3) Editorial: source-name context follows the explicit named-source setting, not channel naming.
path = "telegram_autopilot/v2/editorial.py"
text = read(path)
text = replace_once(
    text,
    'from .community_context import community_body_hard_limit, community_source_name, require_community_context',
    'from .source_attribution import source_body_hard_limit, source_context_name, require_source_context',
    "editorial import",
)
text = text.replace("community_source_name", "source_context_name")
text = text.replace("community_body_hard_limit", "source_body_hard_limit")
text = text.replace("require_community_context", "require_source_context")
text = text.replace("community_name", "source_context")
text = text.replace("community_instruction", "source_context_instruction")
text = text.replace("COMMUNITY CONTEXT:", "SOURCE CONTEXT:")
text = text.replace(
    'Не замінюй її лише безликими словами «громада» або «мешканці громади».\\n',
    'Не замінюй її безликим описом джерела.\\n',
)
text = text.replace(
    'raise ValueError(f"У рерайті втрачено назву громади: {name}")',
    'raise ValueError(f"У рерайті втрачено назву джерела: {name}")',
)
write(path, text)


# 4) Publisher imports the generic attribution module.
path = "telegram_autopilot/v2/publisher.py"
text = read(path)
text = replace_once(
    text,
    "from .community_context import attribution_for_article",
    "from .source_attribution import attribution_for_article",
    "publisher import",
)
write(path, text)


# 5) Storage: real channel field + safe schema upgrade + one-time RC34 compatibility migration.
path = "telegram_autopilot/v2/storage.py"
text = read(path)
text = replace_once(
    text,
    "from .domain import AIModelHealth, BlockedBy, ChannelConfig, ChannelMode, ChannelPolicy, Decision, ProviderHealth, ProviderState, Stage",
    "from .domain import AIModelHealth, BlockedBy, ChannelConfig, ChannelMode, ChannelPolicy, Decision, ProviderHealth, ProviderState, SourceAttributionMode, Stage",
    "storage domain import",
)
text = replace_once(
    text,
    " source_link_required INTEGER NOT NULL DEFAULT 1,poll_interval_minutes INTEGER NOT NULL DEFAULT 5,poll_immediate INTEGER NOT NULL DEFAULT 0,",
    " source_link_required INTEGER NOT NULL DEFAULT 1,source_attribution_mode TEXT NOT NULL DEFAULT 'standard',poll_interval_minutes INTEGER NOT NULL DEFAULT 5,poll_immediate INTEGER NOT NULL DEFAULT 0,",
    "storage schema field",
)
text = replace_once(
    text,
    '            with self.connect() as con:\n                con.executescript(SCHEMA); con.execute("INSERT INTO meta(key,value) VALUES(\'schema_version\',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(str(V2_SCHEMA_VERSION),))\n\n    def run_startup_maintenance',
    '''            with self.connect() as con:\n                con.executescript(SCHEMA)\n                self._ensure_source_attribution_mode(con)\n                con.execute("INSERT INTO meta(key,value) VALUES('schema_version',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(str(V2_SCHEMA_VERSION),))\n\n    @staticmethod\n    def _ensure_source_attribution_mode(con: sqlite3.Connection) -> None:\n        """Add RC35 channel setting and preserve RC34 behavior once for existing channels.\n\n        The name check exists only in this one-time compatibility migration. Runtime\n        behavior never derives attribution from a channel name; future channels default\n        to ``standard`` until the operator changes the visible channel setting.\n        """\n        columns = {str(row[1]) for row in con.execute("PRAGMA table_info(channels)").fetchall()}\n        if "source_attribution_mode" not in columns:\n            con.execute("ALTER TABLE channels ADD COLUMN source_attribution_mode TEXT NOT NULL DEFAULT 'standard'")\n        key = "rc35_explicit_source_attribution_mode_v1"\n        done = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()\n        if done and str(done[0] or "") == "1":\n            return\n        con.execute(\n            """UPDATE channels SET source_attribution_mode=?\n               WHERE channel_mode='monitoring'\n                 AND source_attribution_mode='standard'\n                 AND instr(lower(name),'громад')>0""",\n            (str(SourceAttributionMode.NAMED_SOURCE),),\n        )\n        con.execute(\n            "INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",\n            (key, "1"),\n        )\n\n    def run_startup_maintenance''',
    "storage initialize migration",
)
text = replace_once(
    text,
    '        mode=ChannelMode.MONITORING if str(row["channel_mode"]).casefold()=="monitoring" else ChannelMode.EDITORIAL\n        return ChannelConfig(',
    '''        mode=ChannelMode.MONITORING if str(row["channel_mode"]).casefold()=="monitoring" else ChannelMode.EDITORIAL\n        try:\n            source_attribution_mode=SourceAttributionMode(str(_row_get(row,"source_attribution_mode","standard") or "standard"))\n        except Exception:\n            source_attribution_mode=SourceAttributionMode.STANDARD\n        return ChannelConfig(''',
    "storage load mode",
)
text = replace_once(
    text,
    '            editorial_profile=str(row["editorial_profile"] or ""),include_source_link=_bool(row["include_source_link"],True),source_link_required=_bool(row["source_link_required"],True),\n            poll_interval_minutes=',
    '            editorial_profile=str(row["editorial_profile"] or ""),include_source_link=_bool(row["include_source_link"],True),source_link_required=_bool(row["source_link_required"],True),\n            source_attribution_mode=source_attribution_mode,\n            poll_interval_minutes=',
    "storage ChannelConfig mode",
)
text = replace_once(
    text,
    'con.execute("""UPDATE channels SET name=?,telegram_chat_id=?,enabled=?,channel_mode=?,editorial_profile=?,include_source_link=?,source_link_required=?,poll_interval_minutes=?,poll_immediate=?,min_publish_interval_minutes=?,dedupe_window_hours=?,max_age_hours=?,max_posts_per_cycle=?,publish_24h=?,publish_start=?,publish_end=?,publish_immediately=?,topic_balance_enabled=?,topic_daily_limit=?,related_spacing_posts=?,editorial_weights_json=?,language_mode=?,media_enrichment_mode=?,media_first_allowed=?,media_min_text_chars=?,updated_at=? WHERE id=?""",\n                    (cfg.name,cfg.telegram_chat_id,int(cfg.enabled),str(cfg.mode),cfg.editorial_profile,int(cfg.include_source_link),int(cfg.source_link_required),int(cfg.poll_interval_minutes),int(cfg.poll_immediate),int(cfg.min_publish_interval_minutes),int(cfg.dedupe_window_hours),int(cfg.max_age_hours),int(cfg.max_posts_per_cycle),int(cfg.publish_24h),cfg.publish_start,cfg.publish_end,int(cfg.publish_immediately),int(cfg.topic_balance_enabled),int(cfg.topic_daily_limit),int(cfg.related_spacing_posts),cfg.editorial_weights_json,cfg.language_mode,cfg.media_enrichment_mode,int(cfg.media_first_allowed),int(cfg.media_min_text_chars),stamp,int(cfg.id)))',
    'con.execute("""UPDATE channels SET name=?,telegram_chat_id=?,enabled=?,channel_mode=?,editorial_profile=?,include_source_link=?,source_link_required=?,source_attribution_mode=?,poll_interval_minutes=?,poll_immediate=?,min_publish_interval_minutes=?,dedupe_window_hours=?,max_age_hours=?,max_posts_per_cycle=?,publish_24h=?,publish_start=?,publish_end=?,publish_immediately=?,topic_balance_enabled=?,topic_daily_limit=?,related_spacing_posts=?,editorial_weights_json=?,language_mode=?,media_enrichment_mode=?,media_first_allowed=?,media_min_text_chars=?,updated_at=? WHERE id=?""",\n                    (cfg.name,cfg.telegram_chat_id,int(cfg.enabled),str(cfg.mode),cfg.editorial_profile,int(cfg.include_source_link),int(cfg.source_link_required),str(cfg.source_attribution_mode),int(cfg.poll_interval_minutes),int(cfg.poll_immediate),int(cfg.min_publish_interval_minutes),int(cfg.dedupe_window_hours),int(cfg.max_age_hours),int(cfg.max_posts_per_cycle),int(cfg.publish_24h),cfg.publish_start,cfg.publish_end,int(cfg.publish_immediately),int(cfg.topic_balance_enabled),int(cfg.topic_daily_limit),int(cfg.related_spacing_posts),cfg.editorial_weights_json,cfg.language_mode,cfg.media_enrichment_mode,int(cfg.media_first_allowed),int(cfg.media_min_text_chars),stamp,int(cfg.id)))',
    "storage save mode",
)
write(path, text)


# 6) UI: expose the setting in the channel dialog.
path = "telegram_autopilot/v2/ui.py"
text = read(path)
text = replace_once(
    text,
    "from .domain import ChannelConfig, ChannelMode, ChannelPolicy",
    "from .domain import ChannelConfig, ChannelMode, ChannelPolicy, SourceAttributionMode",
    "ui import",
)
anchor = 'PROVIDER_UA = {\n'
pos = text.find(anchor)
if pos < 0:
    raise RuntimeError("ui provider anchor missing")
end = text.find("\n}\n\n\nclass ChannelDialog", pos)
if end < 0:
    raise RuntimeError("ui provider block end missing")
end += 3
mapping = '''\nATTRIBUTION_MODE_LABELS = {\n    SourceAttributionMode.STANDARD: "Стандартне — Джерело",\n    SourceAttributionMode.NAMED_SOURCE: "Іменоване — Читати у «назва джерела»",\n}\nATTRIBUTION_MODE_VALUES = {label: mode for mode, label in ATTRIBUTION_MODE_LABELS.items()}\n'''
text = text[:end] + mapping + text[end:]
text = replace_once(
    text,
    '        self._entry(p, 16, "Media-first поріг тексту", cfg.media_min_text_chars)\n        ttk.Label(p, text="Джерело є обов\'язковим для READY/PUBLISH і не може бути вимкнене.").grid(row=17, column=0, columnspan=2, sticky="w", padx=6, pady=10)',
    '''        self._entry(p, 16, "Media-first поріг тексту", cfg.media_min_text_chars)\n        self._combo(\n            p, 17, "Формат посилання на джерело",\n            ATTRIBUTION_MODE_LABELS.get(cfg.source_attribution_mode, ATTRIBUTION_MODE_LABELS[SourceAttributionMode.STANDARD]),\n            list(ATTRIBUTION_MODE_VALUES),\n        )\n        ttk.Label(\n            p,\n            text="Стандартне: Джерело / Джерело N. Іменоване: Читати у «назва джерела»; назва джерела також зберігається як обов'язковий контекст рерайту.",\n            wraplength=760, foreground="#444",\n        ).grid(row=18, column=0, columnspan=2, sticky="w", padx=6, pady=8)\n        ttk.Label(p, text="Джерело є обов'язковим для READY/PUBLISH і не може бути вимкнене.").grid(row=19, column=0, columnspan=2, sticky="w", padx=6, pady=6)''',
    "ui source attribution combo",
)
text = replace_once(
    text,
    '                source_link_required=True,\n                poll_interval_minutes=',
    '                source_link_required=True,\n                source_attribution_mode=ATTRIBUTION_MODE_VALUES.get(self._get("Формат посилання на джерело"), SourceAttributionMode.STANDARD),\n                poll_interval_minutes=',
    "ui save mode",
)
write(path, text)


# 7) Regression tests: explicit setting wins; channel name alone no longer changes behavior.
old_test = ROOT / "tests/test_v2_rc34_community_context.py"
if old_test.exists():
    old_test.unlink()
write(
    "tests/test_v2_rc35_channel_attribution.py",
    '''from __future__ import annotations

import json
import sqlite3

import pytest

from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode, SourceAttributionMode
from telegram_autopilot.v2.editorial import validate_writer_output
from telegram_autopilot.v2.source_attribution import (
    attribution_for_article,
    source_body_hard_limit,
    source_context_name,
    source_footer_label,
)
from telegram_autopilot.v2.storage import V2Store
from telegram_autopilot.v2.telegram_attribution import _attribution_entities, build_attributed_post_text


def _named_channel(name: str = "ЗАПОРІЖЖЯ | ГРОМАДИ") -> ChannelConfig:
    return ChannelConfig(
        id=3,
        name=name,
        telegram_chat_id="@named_source_test",
        mode=ChannelMode.MONITORING,
        source_attribution_mode=SourceAttributionMode.NAMED_SOURCE,
    )


def test_channel_name_alone_no_longer_enables_named_attribution() -> None:
    channel = ChannelConfig(id=3, name="ЗАПОРІЖЖЯ | ГРОМАДИ", telegram_chat_id="@test")
    article = {"source_name": "Кушугумська громада"}
    assert source_context_name(channel, article) == ""
    assert source_footer_label(channel, article) == ""
    assert source_body_hard_limit(channel, article) == 880


def test_explicit_named_source_mode_is_generic_not_community_specific() -> None:
    channel = _named_channel("МОНІТОРИНГ ОФІЦІЙНИХ ДЖЕРЕЛ")
    article = {"source_name": "Міністерство цифрової трансформації"}
    assert source_context_name(channel, article) == "Міністерство цифрової трансформації"
    assert source_footer_label(channel, article) == "Читати у «Міністерство цифрової трансформації»"
    assert source_body_hard_limit(channel, article) < 880


def test_named_footer_uses_exact_primary_original_post_only() -> None:
    channel = _named_channel()
    article = {"source_name": "Кушугумська громада"}
    original = "https://t.me/kushugum_hromada/123"
    evidence = "https://example.org/background"
    urls, labels = attribution_for_article(channel, article, source_url=original, source_urls=[original, evidence])
    assert urls == [original]
    assert labels == ["Читати у «Кушугумська громада»"]
    post = build_attributed_post_text(
        "Кушугумська громада повідомила мешканцям про нову можливість долучитися до життя громади.",
        source_url=original,
        source_urls=urls,
        source_labels=labels,
        include_source_link=True,
        hard_limit=900,
    )
    assert post.endswith("Читати у «Кушугумська громада»")
    assert "\\n\\nДжерело" not in post
    entities = json.loads(_attribution_entities(post, original, urls, labels))
    links = [item for item in entities if item.get("type") == "text_link"]
    assert len(links) == 1
    assert links[0]["url"] == original


def test_standard_mode_keeps_generic_attribution_even_for_communities_name() -> None:
    channel = ChannelConfig(id=3, name="ЗАПОРІЖЖЯ | ГРОМАДИ", telegram_chat_id="@test")
    article = {"source_name": "Кушугумська громада"}
    primary = "https://example.org/story"
    extra = "https://example.net/evidence"
    urls, labels = attribution_for_article(channel, article, source_url=primary, source_urls=[primary, extra])
    assert urls == [primary, extra]
    assert labels is None
    post = build_attributed_post_text(
        "Це достатньо довгий тестовий текст українською для перевірки стандартної атрибуції каналу.",
        source_url=primary,
        source_urls=urls,
        source_labels=labels,
        include_source_link=True,
        hard_limit=900,
    )
    assert post.endswith("Джерело 1\\nДжерело 2")


def test_writer_qa_requires_explicit_named_source_context_when_requested() -> None:
    article = {
        "source_name": "Кушугумська громада",
        "title": "Як мешканці можуть долучатися до життя громади",
        "raw_text": "Мешканців громади закликають брати участь в опитуваннях, пропонувати власні ідеї та підтримувати волонтерські ініціативи.",
    }
    contextless = "Мешканців громади закликають долучатися до її життя: брати участь в опитуваннях, пропонувати власні ідеї та підтримувати волонтерські ініціативи."
    with pytest.raises(ValueError, match="втрачено назву джерела"):
        validate_writer_output(article, contextless, min_chars=80, max_chars=450, hard_max_chars=850, required_context="Кушугумська громада")


def test_rc35_schema_upgrade_preserves_rc34_communities_behavior_once(tmp_path) -> None:
    db = tmp_path / "old.sqlite3"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE meta (key TEXT PRIMARY KEY,value TEXT NOT NULL)")
        con.execute("CREATE TABLE channels (id INTEGER PRIMARY KEY,name TEXT NOT NULL,channel_mode TEXT NOT NULL DEFAULT 'editorial')")
        con.execute("INSERT INTO channels(id,name,channel_mode) VALUES(3,'ЗАПОРІЖЖЯ | ГРОМАДИ','monitoring')")
    V2Store(db)
    with sqlite3.connect(db) as con:
        columns = {row[1] for row in con.execute("PRAGMA table_info(channels)")}
        mode = con.execute("SELECT source_attribution_mode FROM channels WHERE id=3").fetchone()[0]
        marker = con.execute("SELECT value FROM meta WHERE key='rc35_explicit_source_attribution_mode_v1'").fetchone()[0]
    assert "source_attribution_mode" in columns
    assert mode == "named_source"
    assert marker == "1"
''',
)


# 8) Version and release metadata.
for name in ("VERSION.txt", "PUBLIC_VERSION.txt", "V2_VERSION.txt"):
    write(name, "2.0.0-rc35\n")

path = "telegram_autopilot/__init__.py"
text = read(path).replace('__version__ = "2.0.0-rc34"', '__version__ = "2.0.0-rc35"')
write(path, text)

path = "telegram_autopilot/v2/__init__.py"
text = read(path).replace('V2_VERSION = "2.0.0-rc34"', 'V2_VERSION = "2.0.0-rc35"')
write(path, text)

path = "pyproject.toml"
text = read(path).replace('version = "2.0.0rc28"', 'version = "2.0.0rc35"')
write(path, text)

write(
    "RELEASE_NOTES_v2.0.0-rc35.md",
    '''# UA FREE Telegram Autopilot v2.0.0-rc35

## Explicit per-channel source attribution

RC35 removes the RC34 runtime heuristic that inferred community behavior from an output channel name.

### What changed

- Added a visible per-channel setting: `Формат посилання на джерело`.
- `Стандартне — Джерело` keeps the existing generic `Джерело` / `Джерело N` footer.
- `Іменоване — Читати у «назва джерела»` uses the configured donor/source name and links it to the exact primary original post.
- Named-source mode also makes the configured source name mandatory rewrite context, so context is preserved outside the donor channel.
- Runtime behavior no longer checks whether a channel name contains `громад` or any other keyword.
- Future monitoring channels default to `standard`; they do not inherit community semantics.
- Existing RC34 databases receive a one-time compatibility migration: monitoring channels that previously matched the RC34 `громад` heuristic are stored as `named_source`. After that migration, the database setting is authoritative and editable in the channel UI.
- Actionable registration/form/payment/schedule URLs remain protected independently and stay in the post body.

### Compatibility

- No destructive database migration.
- Existing articles, sources, publication history, feedback and credentials are preserved.
- RC34 imports remain import-safe through a compatibility shim, but no name-based runtime detection remains.
''',
)

# Remove the one-time patcher and workflow from the resulting source tree.
for transient in (ROOT / "tools/rc35_apply.py", ROOT / ".github/workflows/rc35-apply.yml"):
    if transient.exists():
        transient.unlink()

print("RC35_PATCH_APPLIED")
