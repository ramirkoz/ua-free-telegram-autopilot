from __future__ import annotations

import re
from typing import Any

from .dedupe import DedupeResult
from .domain import Decision, DedupeProfile, Stage
from .loghub import event
from .semantic_dedupe import (
    SemanticDedupeEngine,
    SemanticGuardedPublisher as _BaseSemanticGuardedPublisher,
    _concept_sequence,
    _value,
    semantic_same_event,
)

# RC56: event-identity dedupe.  The matcher deliberately distinguishes identity
# anchors (proper/scientific names, methods/mechanisms, facts) from generic topic
# vocabulary so commercial-editorial channels are not collapsed merely because two articles both discuss
# marketing while channels with scientific dedupe enabled can still catch aggressively rewritten reports of one
# scientific study/event.
_NUMBER_RE = re.compile(r"(?<![\w])\d+(?:[.,]\d+)?(?:\s*%|\s*відсот(?:ок|ки|ків)?)?", re.I)
_QUANTITY_RE = re.compile(
    r"(?<![\w])(?P<num>\d{1,3}(?:[\s\u00a0]\d{3})+|\d+(?:[.,]\d+)?)"
    r"\s*(?P<unit>млрд\.?|мільярд\w*|billion|bn|млн\.?|мільйон\w*|million|тис\.?|тисяч\w*|thousand|k)?",
    re.I,
)
_NAMED_ENTITY_RE = re.compile(r"\b(?:[A-Z][A-Za-z0-9&+.-]{2,}|[A-Z]{2,10})\b")
_SCIENTIFIC_BINOMIAL_RE = re.compile(r"\b([A-Z][a-z]{3,})\s+([a-z][a-z-]{3,})\b")

_ENTITY_STOP = {
    "the", "and", "for", "with", "from", "this", "that", "into", "about", "after", "before",
    "data", "media", "image", "images", "video", "videos", "camera", "cameras", "server", "servers",
    "company", "device", "devices", "system", "systems", "cloud", "http", "https", "www", "com", "org",
    "news", "report", "study", "research", "security", "police", "city", "cities", "state", "states",
    "according", "actually", "already", "also", "another", "around", "because", "content", "comes",
    "coming", "create", "creating", "deals", "director", "environment", "events", "execs", "fact", "feel",
    "forms", "ghost", "have", "helps", "including", "influencer", "just", "know", "latest", "like", "little",
    "looking", "marketers", "marketing", "might", "more", "other", "paid", "partner", "piece", "place",
    "provides", "real", "really", "said", "several", "show", "showing", "some", "still", "tech", "terms",
    "than", "their", "them", "there", "they", "told", "traditional", "true", "used", "very", "want", "well",
    "were", "where", "would",
}

_SCIENTIFIC_CONTEXT = (
    "species", "taxon", "genus", "scientific name", "binomial", "subspecies",
    "вид", "таксон", "рід", "латинська назва", "біологічний вид",
)
_SCIENTIFIC_CONTEXT_RE = re.compile(
    r"(?:\b(?:new|newly\s+described|undescribed|distinct)\s+species\b"
    r"|\bspecies\b|\bgenus\b|\btaxon(?:omy|omic|on)?\b|\bbinomial\b|\bscientific\s+name\b|\bsubspecies\b"
    r"|\b(?:нов(?:ий|ого|а|у)|невідом(?:ий|ого|а|у))\s+вид\w*\b|\bвид(?:у|ом|и|ів)?\b|\bтаксон\w*\b|\bрід\b"
    r"|\bлатинськ\w*\s+назв\w*\b|\bбіологічн\w*\s+вид\w*\b)",
    re.I,
)
_SCIENTIFIC_SECOND_STOP = {
    "according", "added", "after", "again", "around", "because", "comes", "could", "found", "helps", "including",
    "looking", "might", "provides", "really", "released", "said", "showing", "still", "their", "there", "these",
    "they", "told", "using", "would", "model", "hope", "science", "podcast", "media", "news", "report",
    "content", "research", "study", "system", "device", "market", "company", "people", "world",
}

_EVENT_ACTION_FAMILIES: dict[str, tuple[str, ...]] = {
    "hack": ("хакер", "злам", "hack", "breach", "hacker"),
    "dismantle": ("розібрал", "розкрив", "розібран", "disassembl", "teardown", "dismantl"),
    "discover": ("знайш", "вияв", "розкрит", "found", "discover", "reveal"),
    "camera": ("камер", "camera"),
    "capture": ("знімк", "фото", "віде", "кадр", "image", "photo", "video", "record"),
    "storage": ("зберіг", "сховищ", "файл", "filesystem", "storage", "stored", "file"),
    "transfer_data": ("передав", "сервер", "cloud", "server", "transmit", "upload"),
    "access": ("доступ", "контрол", "access", "control"),
    "privacy": ("приват", "стеж", "спостереж", "privacy", "surveillance", "tracking"),
    "law_enforcement": ("поліц", "агентств", "служб", "police", "agency", "agencies", "law enforcement"),
    "taxonomy": ("новий вид", "нового виду", "описали вид", "описан вид", "new species", "described species", "taxon"),
    "scan": ("рентген", "x-ray", "xray", "tomograph", "скан", "scan", "spectrom"),
    "digital_read": ("цифров", "розгорт", "розшифр", "unroll", "digitiz", "decipher"),
}

_RARE_STOP = {
    "дослідники", "дослідження", "науковці", "вчені", "результати", "показали",
    "researchers", "research", "scientists", "study", "results", "using", "based",
}

# Broad topic/boilerplate concepts must never become event-identity anchors by
# themselves.  Prefixes are used because ``_concept_sequence`` stems words.
_COMPOUND_GENERIC_ROOTS = (
    "research", "scient", "study", "report", "result", "analysis", "testing", "test",
    "company", "system", "device", "market", "security", "data", "cloud", "server", "access",
    "content", "product", "model", "technology", "platform", "service", "method", "process",
    "event", "unique", "user", "people", "world", "news", "article", "information",
    "дослід", "науков", "вчен", "результ", "аналіз", "тест", "компан", "систем", "пристр",
    "ринок", "безпек", "дан", "сервер", "доступ", "контент", "продукт", "модел", "технолог",
    "платформ", "сервіс", "метод", "процес", "поді", "новин", "статт", "інформац",
)


def _is_generic_identity_term(term: str) -> bool:
    value = str(term or "").casefold().strip(".'’-_")
    return (not value) or any(value.startswith(root) for root in _COMPOUND_GENERIC_ROOTS)

_WORD_NUMBERS = {
    "один": 1, "одна": 1, "одне": 1, "два": 2, "дві": 2, "три": 3, "чотири": 4,
    "п'ять": 5, "п’ять": 5, "пять": 5, "шість": 6, "сім": 7, "вісім": 8, "дев'ять": 9,
    "дев’ять": 9, "десять": 10, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
_DURATION_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яІіЇїЄєҐґ0-9'’.,]+")


def _value_text(row: Any) -> str:
    return "\n".join(
        str(_value(row, key, "") or "")
        for key in ("title", "raw_text", "final_text", "event_summary")
    )


def _numbers(value: str) -> list[float]:
    out: list[float] = []
    for match in _NUMBER_RE.finditer(value):
        token = match.group(0).casefold().replace("відсотків", "").replace("відсотки", "").replace("відсоток", "").replace("%", "").strip()
        try:
            number = float(token.replace(",", "."))
        except ValueError:
            continue
        if 1900 <= number <= 2100 and number.is_integer():
            continue
        if 0 < number < 1:
            continue
        out.append(number)
    return out[:24]


def _near_numeric_pairs(left: str, right: str) -> list[tuple[float, float]]:
    """Return only genuinely compatible numeric anchors.

    RC60 used an absolute tolerance of two for every small number, so unrelated
    facts such as 3 vs 1 or 12 vs 11 became corroborating evidence.  Small
    counts now need to be effectively equal; percentages / larger measurements
    still allow a narrow relative tolerance (for example 90 vs 92 percent).
    """
    pairs: list[tuple[float, float]] = []
    for a in _numbers(left):
        for b in _numbers(right):
            scale = max(abs(a), abs(b))
            if scale < 20:
                tolerance = 0.25
            elif scale <= 100:
                tolerance = max(1.0, 0.03 * scale)
            else:
                tolerance = max(1.0, 0.02 * scale)
            if abs(a - b) <= tolerance:
                pairs.append((a, b))
                break
    return pairs


def _quantity_values(value: str) -> list[float]:
    out: list[float] = []
    for match in _QUANTITY_RE.finditer(str(value or "")):
        raw = match.group("num").replace("\u00a0", " ").replace(" ", "")
        try:
            number = float(raw.replace(",", "."))
        except ValueError:
            continue
        unit = (match.group("unit") or "").casefold().rstrip(".")
        multiplier = 1.0
        if unit.startswith(("млрд", "мільярд")) or unit in {"billion", "bn"}:
            multiplier = 1_000_000_000.0
        elif unit.startswith(("млн", "мільйон")) or unit == "million":
            multiplier = 1_000_000.0
        elif unit.startswith(("тис", "тисяч")) or unit in {"thousand", "k"}:
            multiplier = 1_000.0
        normalized = number * multiplier
        if 1900 <= normalized <= 2100 and normalized.is_integer() and multiplier == 1.0:
            continue
        if normalized <= 0:
            continue
        out.append(normalized)
    unique: list[float] = []
    for number in out:
        if not any(abs(number - old) <= max(1.0, abs(number) * 0.001) for old in unique):
            unique.append(number)
    return unique[:32]


def _near_quantity_pairs(left: str, right: str) -> list[tuple[float, float]]:
    pairs: list[tuple[float, float]] = []
    used: set[int] = set()
    right_values = _quantity_values(right)
    for a in _quantity_values(left):
        for index, b in enumerate(right_values):
            if index in used:
                continue
            scale = max(abs(a), abs(b))
            if scale < 20:
                tolerance = 0.25
            elif scale <= 100:
                tolerance = max(1.0, 0.03 * scale)
            else:
                tolerance = max(1.0, 0.02 * scale)
            if abs(a - b) <= tolerance:
                pairs.append((a, b))
                used.add(index)
                break
    return pairs


def _duration_days(value: str) -> list[float]:
    tokens = [token.casefold().strip(".,") for token in _DURATION_TOKEN_RE.findall(str(value or ""))]
    out: list[float] = []
    for index in range(len(tokens) - 1):
        first, unit = tokens[index], tokens[index + 1]
        try:
            amount = float(first.replace(",", "."))
        except ValueError:
            amount = float(_WORD_NUMBERS.get(first, 0))
        if amount <= 0:
            continue
        factor = None
        if unit.startswith(("дн", "ден", "day")):
            factor = 1.0
        elif unit.startswith(("тиж", "week")):
            factor = 7.0
        elif unit.startswith(("годин", "hour")):
            factor = 1.0 / 24.0
        elif unit.startswith(("місяц", "month")):
            factor = 30.0
        if factor is not None:
            out.append(amount * factor)
    return out[:16]


def _near_duration_pairs(left: str, right: str) -> list[tuple[float, float]]:
    pairs: list[tuple[float, float]] = []
    for a in _duration_days(left):
        for b in _duration_days(right):
            tolerance = max(1.0, 0.08 * max(abs(a), abs(b)))
            if abs(a - b) <= tolerance:
                pairs.append((a, b))
                break
    return pairs


def _entity_tokens(value: str) -> set[str]:
    """Extract actual proper-name-ish entities, not every English word.

    RC53 accidentally treated all Latin words as entities.  That was useful for a
    Flock regression but caused PRODANO false positives where ordinary words like
    marketing/said/content became an enormous fake entity set.
    """
    entities: set[str] = set()
    for token in _NAMED_ENTITY_RE.findall(str(value or "")):
        normalized = token.casefold().strip(".-")
        if len(normalized) < 4 or normalized in _ENTITY_STOP or normalized.isdigit():
            continue
        entities.add(normalized)
    return entities


def _scientific_names(value: str) -> set[str]:
    """Extract a Latin binomial only when explicit taxonomy language is nearby.

    Generic research words are intentionally *not* taxonomy evidence.  That
    prevents phrases such as ``Machine Learning``, ``Read More`` or ``Share This``
    from becoming fake species merely because an article also says "researchers".
    """
    raw = str(value or "")
    out: set[str] = set()
    for match in _SCIENTIFIC_BINOMIAL_RE.finditer(raw):
        first, second = match.group(1), match.group(2)
        first_low, second_low = first.casefold(), second.casefold()
        if second_low in _SCIENTIFIC_SECOND_STOP or first_low in _ENTITY_STOP:
            continue
        start = max(0, match.start() - 150)
        end = min(len(raw), match.end() + 150)
        local = raw[start:end]
        if not _SCIENTIFIC_CONTEXT_RE.search(local):
            continue
        out.add(f"{first_low} {second_low}")
    return out


def _action_hits(value: str) -> set[str]:
    return {family for family, roots in _EVENT_ACTION_FAMILIES.items() if any(root in value for root in roots)}


def _rare_terms(value: str) -> set[str]:
    terms: set[str] = set()
    for token in _concept_sequence(value):
        term = str(token or "").casefold().strip(".'’-_")
        if len(term) < 7 or term in _RARE_STOP or term.isdigit() or _is_generic_identity_term(term):
            continue
        terms.add(term)
    return terms


def _identity_text(row: Any) -> str:
    """Compact event-bearing text used by high-precision fingerprints.

    Full scraped pages often contain navigation, recommendations and repeated
    site boilerplate.  Comparing 14k characters of that material made unrelated
    stories look similar.  Identity matching is therefore limited to the title,
    event summary and the leading editorial/source text where the event itself is
    normally stated.
    """
    title = str(_value(row, "title", "") or "").strip()
    summary = str(_value(row, "event_summary", "") or "").strip()
    final_text = str(_value(row, "final_text", "") or "").strip()
    raw_text = str(_value(row, "raw_text", "") or "").strip()
    parts = [title, summary]
    if final_text:
        parts.append(final_text[:2200])
    if raw_text:
        parts.append(raw_text[:2200])
    return "\n".join(part for part in parts if part)[:5200]


def _fingerprint_stats(current: Any, candidate: Any) -> dict[str, Any]:
    left_raw = _identity_text(current)
    right_raw = _identity_text(candidate)
    left = left_raw.casefold()
    right = right_raw.casefold()
    concepts_a = set(_concept_sequence(left))
    concepts_b = set(_concept_sequence(right))
    shared = concepts_a & concepts_b
    containment = len(shared) / max(1, min(len(concepts_a), len(concepts_b)))
    salient_a = {term for term in concepts_a if len(term) >= 5 and not _is_generic_identity_term(term)}
    salient_b = {term for term in concepts_b if len(term) >= 5 and not _is_generic_identity_term(term)}
    salient_shared = salient_a & salient_b
    salient_containment = len(salient_shared) / max(1, min(len(salient_a), len(salient_b)))
    return {
        "left_raw": left_raw,
        "right_raw": right_raw,
        "left": left,
        "right": right,
        "shared": shared,
        "containment": containment,
        "long_shared": {item for item in shared if len(item) >= 6},
        "salient_shared": salient_shared,
        "salient_containment": salient_containment,
        "salient_long_shared": {item for item in salient_shared if len(item) >= 6},
        "numeric_pairs": _near_numeric_pairs(left, right),
        "quantity_pairs": _near_quantity_pairs(left, right),
        "duration_pairs": _near_duration_pairs(left, right),
        "shared_entities": _entity_tokens(left_raw) & _entity_tokens(right_raw),
        "shared_scientific": _scientific_names(left_raw) & _scientific_names(right_raw),
        "shared_actions": _action_hits(left) & _action_hits(right),
        "shared_rare": _rare_terms(left) & _rare_terms(right),
    }


def event_fingerprint_same_event(
    current: Any,
    candidate: Any,
    *,
    scientific_names: bool = False,
    compound_events: bool = False,
    rare_terms: bool = False,
    commercial_profile: bool = False,
) -> tuple[bool, str]:
    """High-precision event equivalence controlled only by channel settings.

    Concrete stories are regression fixtures, never production rules. The matcher
    combines generic scientific names, concepts, rare terms, proper names, actions
    and normalized facts.
    """
    same, reason = semantic_same_event(current, candidate)
    if same:
        return True, reason
    if reason.startswith("conflicting strong event/version/product codes"):
        return False, reason

    same_source = int(_value(current, "source_id", 0) or 0) == int(_value(candidate, "source_id", 0) or -1)
    stats = _fingerprint_stats(current, candidate)
    shared = stats["shared"]
    containment = float(stats["containment"])
    long_shared = stats["long_shared"]
    salient_shared = stats["salient_shared"]
    salient_containment = float(stats["salient_containment"])
    salient_long_shared = stats["salient_long_shared"]
    numeric_pairs = stats["numeric_pairs"]
    quantity_pairs = stats["quantity_pairs"]
    duration_pairs = stats["duration_pairs"]
    shared_entities = stats["shared_entities"]
    shared_scientific = stats["shared_scientific"]
    shared_actions = stats["shared_actions"]
    shared_rare = stats["shared_rare"] if rare_terms else set()

    # Exact Latin binomials are high-information identifiers, but only channels that
    # explicitly enable the scientific-name fingerprint use this lane.
    if scientific_names and shared_scientific:
        scientific_corroborated = bool(shared_actions) or (salient_containment >= 0.32 and len(salient_long_shared) >= 4)
        if scientific_corroborated:
            return True, (
                "scientific-name event fingerprint "
                f"taxa={','.join(sorted(shared_scientific))} actions={','.join(sorted(shared_actions)) or '-'} "
                f"concepts={len(shared)}/{containment:.2f}"
            )

    # Generic subject + method/mechanism lane. It deliberately does not contain names
    # of particular discoveries, scrolls, species or experiments. Rare shared concepts
    # and independent fact anchors provide the corroboration.
    if compound_events:
        corroboration = bool(numeric_pairs or quantity_pairs or duration_pairs) or len(shared_rare) >= 3
        strong_rare = len(shared_rare) >= 4
        if (
            len(salient_shared) >= 4
            and salient_containment >= 0.30
            and len(salient_long_shared) >= 3
            and corroboration
        ) or (
            len(salient_shared) >= 4
            and salient_containment >= 0.35
            and len(salient_long_shared) >= 3
            and strong_rare
            and len(shared_actions) >= 2
        ):
            return True, (
                "compound subject+method+mechanism fingerprint "
                f"concepts={len(shared)}/{containment:.2f} salient={len(salient_shared)}/{salient_containment:.2f} rare={len(shared_rare)} "
                f"numbers={numeric_pairs[:3]} quantities={quantity_pairs[:3]} durations={duration_pairs[:3]}"
            )

        # A proper-name incident skeleton catches heavy rewrites while still requiring
        # multiple independent actions and substantial conceptual overlap.
        if shared_entities and len(shared_actions) >= 2:
            if len(salient_shared) >= 6 and salient_containment >= 0.35 and len(salient_long_shared) >= 4:
                return True, (
                    "named-entity incident fingerprint "
                    f"entities={','.join(sorted(shared_entities))} actions={','.join(sorted(shared_actions))} "
                    f"concepts={len(shared)}/{containment:.2f} salient={len(salient_shared)}/{salient_containment:.2f}"
                )

    # Proper-name + normalized fact lane is useful globally. Commercial channels use
    # stricter thresholds, selected by their explicit dedupe profile.
    if shared_entities and (quantity_pairs or duration_pairs):
        required_actions = 4 if same_source else 3
        required_shared = 7 if same_source else 6
        min_containment = 0.28
        if commercial_profile:
            required_actions = max(required_actions, 3)
            required_shared = max(required_shared, 8)
            min_containment = 0.32
        if (
            len(shared_actions) >= required_actions
            and len(salient_shared) >= max(4, required_shared - 2)
            and salient_containment >= min_containment
            and len(salient_long_shared) >= 3
        ):
            return True, (
                "entity+fact event fingerprint "
                f"entities={','.join(sorted(shared_entities))} actions={','.join(sorted(shared_actions))} "
                f"concepts={len(shared)}/{containment:.2f} quantities={quantity_pairs[:3]} durations={duration_pairs[:3]}"
            )

    anchor_count = len(quantity_pairs) + len(duration_pairs)
    if (
        anchor_count >= 2
        and len(shared_actions) >= 3
        and len(salient_shared) >= 5
        and salient_containment >= 0.32
        and len(salient_long_shared) >= 4
    ):
        return True, (
            "multi-fact event fingerprint "
            f"actions={','.join(sorted(shared_actions))} concepts={len(shared)}/{containment:.2f} "
            f"quantities={quantity_pairs[:4]} durations={duration_pairs[:3]}"
        )

    # Broad numeric similarity is disabled only by an explicit Commercial / Editorial
    # profile. No channel ID or name is consulted here.
    if (
        not commercial_profile
        and numeric_pairs
        and len(salient_shared) >= 7
        and salient_containment >= 0.34
        and len(salient_long_shared) >= 5
    ):
        return True, (
            "concept+numeric event fingerprint "
            f"concepts={len(shared)}/{containment:.2f} long={len(long_shared)} numbers={numeric_pairs[:3]}"
        )

    return False, (
        f"{reason}; event fingerprint concepts={len(shared)}/{containment:.2f} salient={len(salient_shared)}/{salient_containment:.2f} "
        f"long={len(long_shared)} taxa={','.join(sorted(shared_scientific)) or '-'} "
        f"entities={','.join(sorted(shared_entities)) or '-'} actions={','.join(sorted(shared_actions)) or '-'} "
        f"rare={len(shared_rare)} numbers={numeric_pairs[:3]} quantities={quantity_pairs[:3]} durations={duration_pairs[:3]}"
    )


class EventFingerprintDedupeEngine(SemanticDedupeEngine):
    """Semantic dedupe plus a channel-configured durable published-event ledger."""

    LEDGER_LIMIT = 2000

    def __init__(self, store):
        super().__init__(store)
        self._ensure_ledger()

    def _ensure_ledger(self) -> None:
        with self.store.connect() as con:
            con.execute(
                """CREATE TABLE IF NOT EXISTS published_event_ledger(
                    ledger_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id INTEGER NOT NULL,
                    article_id INTEGER NOT NULL,
                    source_id INTEGER NOT NULL DEFAULT 0,
                    published_at TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL DEFAULT '',
                    raw_text TEXT NOT NULL DEFAULT '',
                    final_text TEXT NOT NULL DEFAULT '',
                    event_summary TEXT NOT NULL DEFAULT '',
                    source_name TEXT NOT NULL DEFAULT '',
                    UNIQUE(channel_id, article_id)
                )"""
            )
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_published_event_ledger_channel_time ON published_event_ledger(channel_id,published_at DESC)"
            )
            con.commit()

    def _sync_ledger(self, channel_id: int, hours: int | None = None) -> None:
        """Backfill visible PUBLISHED rows using this channel's configured history window."""
        if hours is None:
            channel = self.store.get_channel(int(channel_id))
            hours = int(channel.published_dedupe_window_hours if channel else 168)
        hours = max(1, int(hours))
        with self.store.connect() as con:
            con.execute(
                """INSERT OR IGNORE INTO published_event_ledger(
                       channel_id,article_id,source_id,published_at,title,raw_text,final_text,event_summary,source_name
                   )
                   SELECT a.channel_id,a.id,a.source_id,
                          CASE WHEN a.published_at<>'' THEN a.published_at ELSE a.discovered_at END,
                          a.title,a.raw_text,a.final_text,a.event_summary,COALESCE(s.name,'')
                   FROM articles a LEFT JOIN sources s ON s.id=a.source_id
                   WHERE a.channel_id=? AND a.stage='PUBLISHED' AND a.decision<>'DUPLICATE'
                     AND datetime(CASE WHEN a.published_at<>'' THEN a.published_at ELSE a.discovered_at END)>=datetime('now',?)""",
                (int(channel_id), f"-{hours} hours"),
            )
            con.execute(
                "DELETE FROM published_event_ledger WHERE channel_id=? AND datetime(published_at)<datetime('now',?)",
                (int(channel_id), f"-{hours} hours"),
            )
            count = int(con.execute("SELECT COUNT(*) FROM published_event_ledger WHERE channel_id=?", (int(channel_id),)).fetchone()[0])
            if count > self.LEDGER_LIMIT:
                con.execute(
                    """DELETE FROM published_event_ledger
                       WHERE ledger_id IN (
                           SELECT ledger_id FROM published_event_ledger WHERE channel_id=?
                           ORDER BY datetime(published_at) ASC, ledger_id ASC LIMIT ?
                       )""",
                    (int(channel_id), count - self.LEDGER_LIMIT),
                )
            con.commit()

    def sync_all_published_ledger(self) -> int:
        total = 0
        for channel in self.store.list_channels(enabled_only=False):
            channel_id = int(channel["id"] if not hasattr(channel, "id") else channel.id)
            channel_cfg = self.store.get_channel(channel_id)
            hours = int(channel_cfg.published_dedupe_window_hours if channel_cfg else 168)
            self._sync_ledger(channel_id, hours)
        with self.store.connect() as con:
            total = int(con.execute("SELECT COUNT(*) FROM published_event_ledger").fetchone()[0])
        return total

    def record_published(self, article_id: int) -> None:
        row = self.store.get_article(article_id)
        if row is None or str(row["stage"]) != str(Stage.PUBLISHED):
            return
        channel_id = int(row["channel_id"])
        channel_cfg = self.store.get_channel(channel_id)
        hours = int(channel_cfg.published_dedupe_window_hours if channel_cfg else 168)
        self._sync_ledger(channel_id, hours)

    def _ledger_candidates(self, channel_id: int, article_id: int, hours: int) -> list[Any]:
        self._sync_ledger(channel_id, hours)
        with self.store.connect() as con:
            return con.execute(
                """SELECT article_id AS id,channel_id,source_id,title,raw_text,final_text,event_summary,
                          source_name,published_at,'PUBLISHED' AS stage,'PUBLISH' AS decision
                   FROM published_event_ledger
                   WHERE channel_id=? AND article_id<>?
                   ORDER BY datetime(published_at) DESC,ledger_id DESC LIMIT ?""",
                (int(channel_id), int(article_id), self.LEDGER_LIMIT),
            ).fetchall()

    def _find_duplicate(self, article_id: int, *, published_only: bool = False) -> DedupeResult:
        current = self.store.get_article(article_id)
        if current is None:
            raise KeyError(article_id)
        channel_id = int(current["channel_id"])
        channel = self.store.get_channel(channel_id)
        configured_hours = int(channel.dedupe_window_hours if channel else 72)
        published_hours = int(channel.published_dedupe_window_hours if channel else 168)
        hours = max(1, published_hours if published_only else configured_hours)

        if published_only:
            candidates = self._ledger_candidates(channel_id, article_id, hours)
        else:
            candidates = self._candidate_rows(channel_id, int(article_id), hours)

        scientific_names = bool(channel.dedupe_scientific_names) if channel else False
        compound_events = bool(channel.dedupe_compound_events) if channel else False
        rare_terms = bool(channel.dedupe_rare_terms) if channel else False
        commercial_profile = bool(channel and channel.dedupe_profile == DedupeProfile.COMMERCIAL_EDITORIAL)

        best_id = 0
        best_strength = -1.0
        best_summary = ""
        for candidate in candidates:
            try:
                if str(candidate["decision"]) == str(Decision.DUPLICATE):
                    continue
            except Exception:
                pass
            same, match_reason = event_fingerprint_same_event(
                current, candidate,
                scientific_names=scientific_names,
                compound_events=compound_events,
                rare_terms=rare_terms,
                commercial_profile=commercial_profile,
            )
            if same:
                return DedupeResult("DUPLICATE", int(candidate["id"]), match_reason)
            if published_only:
                stats = _fingerprint_stats(current, candidate)
                strength = float(stats["containment"]) * 10.0 + len(stats["shared"]) + 4.0 * len(stats["shared_entities"]) + 8.0 * len(stats["shared_scientific"]) + 1.5 * len(stats["shared_rare"])
                if strength > best_strength:
                    best_strength = strength
                    best_id = int(candidate["id"])
                    best_summary = (
                        f"concepts={len(stats['shared'])}/{float(stats['containment']):.2f} "
                        f"entities={','.join(sorted(stats['shared_entities'])) or '-'} "
                        f"taxa={','.join(sorted(stats['shared_scientific'])) or '-'} "
                        f"rare={len(stats['shared_rare'])}"
                    )

        if published_only:
            event(
                "publish", "prepublish event trace single", channel_id=channel_id, article_id=article_id,
                nearest_published_article_id=best_id, nearest=best_summary or "none",
            )
        return DedupeResult("SINGLE", None, "no confirmed same event")


class SemanticGuardedPublisher(_BaseSemanticGuardedPublisher):
    def publish_one(self, article_id: int, heartbeat=None) -> str:
        result = super().publish_one(article_id, heartbeat=heartbeat)
        if result == "PUBLISHED" and isinstance(self.semantic_dedupe, EventFingerprintDedupeEngine):
            try:
                self.semantic_dedupe.record_published(article_id)
            except Exception as exc:
                event("publish", "published ledger record failed", level=30, article_id=article_id, detail=str(exc)[:800])
        return result


__all__ = [
    "EventFingerprintDedupeEngine",
    "SemanticGuardedPublisher",
    "event_fingerprint_same_event",
]
