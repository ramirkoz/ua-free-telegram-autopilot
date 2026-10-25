"""2.2.25+ durable, delivery-grounded event memory.

An event is never inferred from a topic, photograph or model-written caption.
Only independently verified source-side incident anchors can authorize a merge.
The initial deterministic matcher is intentionally limited to fatal strikes at
an identifiable site; other stories retain the existing semantic dedupe.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import json
import re
from typing import Any

from .incident_guard import _fatal_count
from .loghub import event


@dataclass(frozen=True)
class EventMatch:
    relation: str = "NEW"  # NEW, DUPLICATE, UPDATE
    prior_article_id: int = 0
    event_id: str = ""
    reason: str = ""


_ATTACK = re.compile(r"(?iu)\b(?:атак\w*|удар\w*|обстріл\w*|обстріля\w*|вдарил\w*)\b")
_PRIVATE = re.compile(r"(?iu)\bприватн\w*\s+(?:(?:житлов\w*|одноповерхов\w*)\s+)?(?:будин\w*|сектор\w*|осел\w*)")
_APARTMENT = re.compile(r"(?iu)\b(?:багатоповерх\w*|багатоквартирн\w*\s+будин\w*)")
_LOCATION = re.compile(
    r"\b(?:у|в|на|біля|поблизу|атакував|атакували|обстріляли|вдарили)\s+"
    r"(?:місті\s+)?([А-ЯІЇЄҐ][а-яіїєґ'-]{4,})"
)
_REVERSE_LOCATION = re.compile(r"\b([А-ЯІЇЄҐ][а-яіїєґ'-]{4,})\s+(?:атакували|обстріляли)\b")
_STREET = re.compile(r"(?iu)\b(?:вул(?:иц[яі])?\.?|провул(?:ок|ку)|просп(?:ект|екті)?\.?)\s+([а-яіїєґ'-]{4,})")
_SEPARATE = re.compile(r"(?iu)\b(?:ще\s+один|інший|новий|повторний)\s+(?:удар|обстріл|атак)")
_CORRECTION = re.compile(r"(?iu)\b(?:уточнил\w*|виправил\w*|спростувал\w*|скоригувал\w*)")


# 2.2.26: another HIGH-CONFIDENCE family only, not generic topic similarity.
# Require a single dated/numbered municipal act, named issuing council and an
# actual issuance/adoption announcement. A report about IMPLEMENTING the act
# is a new event and must not be silenced merely for mentioning its number.
_CIVIC_ACT = re.compile(
    r"(?iu)\b(рішенн\w*|розпоряджен\w*)\s+від\s+"
    r"(\d{1,2}\.\d{1,2}\.\d{4})\s*№\s*(\d[\d/-]{0,12})\b"
)
_CIVIC_ISSUER = re.compile(
    r"\b([А-ЯІЇЄҐ][а-яіїєґ'-]{4,})\s+"
    r"(?:міськ\w*|сільськ\w*|селищн\w*)\s+рад\w*\b"
)
_CIVIC_ADOPTION = re.compile(r"(?iu)\b(?:ухвал\w*|прийня\w*|затверд\w*|видал\w*|оприлюдн\w*)\b")
_CIVIC_PROGRESS = re.compile(
    r"(?iu)\b(?:розпочал\w*|розпочат\w*|стартувал\w*|почал\w*|"
    r"виконал\w*|виплат\w*|отримал\w*|реалізаці\w*|завершил\w*)\b"
)


def _municipal_act_facts(text: str) -> dict[str, Any]:
    # A source title and its body may repeat the same exact document; it
    # remains one act. Two different documents or authorities are ambiguous.
    docs = {
        (m.group(1).casefold(), m.group(2), m.group(3))
        for m in _CIVIC_ACT.finditer(text)
    }
    councils = {_root(m.group(1)) for m in _CIVIC_ISSUER.finditer(text)}
    if len(docs) != 1 or len(councils) != 1:
        return {}
    if not _CIVIC_ADOPTION.search(text) or _CIVIC_PROGRESS.search(text):
        return {}
    kind, document_date, document_number = next(iter(docs))
    return {
        "family": "municipal_act",
        "place": next(iter(councils)),
        "target": kind,
        "document_date": document_date,
        "document_number": document_number,
    }


def _v(row: Any, key: str) -> str:
    try:
        value = row[key]
    except (KeyError, IndexError, TypeError):
        value = getattr(row, key, "")
    return str(value or "")


def _source_text(row: Any) -> str:
    # Never use AI final_text as evidence of incident identity or changed facts.
    return " ".join(x for x in (_v(row, "title"), _v(row, "raw_text")) if x).strip()


def _root(name: str) -> str:
    value = name.casefold().replace("’", "'").strip(" '")
    for suffix in ("ами", "ями", "ій", "ях", "ах", "ою", "ею", "ом", "ем", "ів", "ові", "еві"):
        if len(value) > len(suffix) + 4 and value.endswith(suffix):
            return value[:-len(suffix)]
    if len(value) > 5 and value.endswith(("і", "и", "а", "я", "у", "ю", "о")):
        return value[:-1]
    return value


def _location(text: str) -> str:
    matches = _LOCATION.findall(text) or _REVERSE_LOCATION.findall(text)
    return _root(matches[0]) if matches else ""


def _date(row: Any) -> datetime | None:
    # Ingest/discovery time is not proof of when the underlying event occurred.
    for key in ("source_published_at", "published_at"):
        value = _v(row, key)
        if not value:
            continue
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo:
                return parsed.astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def _facts(row: Any) -> dict[str, Any]:
    text = _source_text(row)
    civic = _municipal_act_facts(text)
    if civic:
        return civic
    # 2.2.31: a daily regional digest may have no named attack site; its
    # original-source report date, strike totals and victim ages are anchors.
    from .regional_daily_event_231 import regional_daily_facts
    daily = regional_daily_facts(row)
    if daily:
        return daily
    fatal = _fatal_count(text)
    if fatal is None or not _ATTACK.search(text):
        return {}
    target = "private_home" if _PRIVATE.search(text) else ("apartment" if _APARTMENT.search(text) else "")
    place = _location(text)
    if not target or not place:
        return {}
    street = _STREET.search(text)
    return {
        "family": "fatal_strike", "place": place, "target": target,
        "street": _root(street.group(1)) if street else "",
        "fatalities": fatal,
        "separate_attack": bool(_SEPARATE.search(text)),
        "correction": bool(_CORRECTION.search(text)),
    }


def _relation(now_row: Any, prior_row: Any) -> str:
    now, prior = _facts(now_row), _facts(prior_row)
    if not now or not prior or now["family"] != prior["family"]:
        return ""
    if (now["place"], now["target"]) != (prior["place"], prior["target"]):
        return ""
    if now["family"] == "regional_daily_attacks":
        from .regional_daily_event_231 import regional_daily_relation
        return regional_daily_relation(now_row, prior_row)
    if now["family"] == "municipal_act":
        if (now["document_date"], now["document_number"]) != (
            prior["document_date"], prior["document_number"]
        ):
            return ""
        a, b = _date(now_row), _date(prior_row)
        return ("DUPLICATE" if a and b and abs(a - b) <= timedelta(hours=48) else "")
    if now["separate_attack"]:
        return ""
    if now["street"] and prior["street"] and now["street"] != prior["street"]:
        return ""
    a, b = _date(now_row), _date(prior_row)
    if not a or not b:
        return ""  # Missing dates cannot be silently treated as fresh.
    gap = abs(a - b)
    if gap > timedelta(hours=48):
        return ""
    if gap > timedelta(hours=4) and not (
        now["street"] and prior["street"] and now["street"] == prior["street"]
    ):
        return ""  # A generic house in a city is not a 48-hour identity anchor.
    if now["fatalities"] > prior["fatalities"]:
        return "UPDATE"
    if now["fatalities"] < prior["fatalities"] and now["correction"]:
        return "UPDATE"
    return "DUPLICATE"


def _ensure(store: Any) -> None:
    with store.connect() as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS event_registry (
            event_id TEXT PRIMARY KEY, channel_id INTEGER NOT NULL,
            first_article_id INTEGER NOT NULL, latest_article_id INTEGER NOT NULL,
            event_family TEXT NOT NULL, location_key TEXT NOT NULL, site_key TEXT NOT NULL,
            latest_facts_json TEXT NOT NULL, last_published_at TEXT NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"""
        )
        con.execute(
            """CREATE TABLE IF NOT EXISTS event_publication_history (
            article_id INTEGER PRIMARY KEY, event_id TEXT NOT NULL,
            channel_id INTEGER NOT NULL, title TEXT NOT NULL, raw_text TEXT NOT NULL,
            source_published_at TEXT NOT NULL, published_at TEXT NOT NULL,
            facts_json TEXT NOT NULL, committed INTEGER NOT NULL DEFAULT 1)"""
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_ev25_channel_time ON event_publication_history(channel_id,published_at DESC)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_ev25_group ON event_publication_history(event_id)")


def _delivered(store: Any, channel_id: int, article_id: int) -> bool:
    with store.connect() as con:
        return con.execute(
            """SELECT 1 WHERE EXISTS (
                SELECT 1 FROM publication_delivery_journal
                WHERE article_id=? AND channel_id=? AND state='COMMITTED'
            ) OR EXISTS (
                SELECT 1 FROM delivery_receipt_archive
                WHERE article_id=? AND channel_id=? AND state='COMMITTED'
            )""",
            (article_id, channel_id, article_id, channel_id),
        ).fetchone() is not None


def find_published_event(store: Any, current: Any, *, window_hours: int = 48) -> EventMatch:
    """Search historical event snapshots and real COMMITTED article deliveries.

    No UNKNOWN, READY or automatic reject can establish a publication.
    """
    if not _facts(current):
        return EventMatch()
    _ensure(store)
    channel_id = int(_v(current, "channel_id") or 0)
    article_id = int(_v(current, "id") or 0)
    hours = min(48, max(1, int(window_hours)))
    with store.connect() as con:
        historical = con.execute(
            """SELECT h.article_id AS id,h.channel_id,h.title,h.raw_text,
                      h.source_published_at,h.published_at,h.event_id
               FROM event_publication_history h
               WHERE h.channel_id=? AND h.article_id<>? AND h.committed=1
                 AND datetime(h.published_at)>=datetime('now',?)
               ORDER BY datetime(h.published_at) DESC LIMIT 300""",
            (channel_id, article_id, f"-{hours} hours"),
        ).fetchall()
        delivered = con.execute(
            """SELECT a.id,a.channel_id,a.title,a.raw_text,a.source_published_at,
                      a.published_at,a.event_key AS event_id
               FROM articles a
               WHERE a.channel_id=? AND a.id<>? AND a.stage='PUBLISHED'
                 AND datetime(a.published_at)>=datetime('now',?)
                 AND (EXISTS (SELECT 1 FROM publication_delivery_journal d
                              WHERE d.article_id=a.id AND d.channel_id=a.channel_id
                                AND d.state='COMMITTED')
                      OR EXISTS (SELECT 1 FROM delivery_receipt_archive h
                                 WHERE h.article_id=a.id AND h.channel_id=a.channel_id
                                   AND h.state='COMMITTED'))
               ORDER BY datetime(a.published_at) DESC LIMIT 300""",
            (channel_id, article_id, f"-{hours} hours"),
        ).fetchall()
    seen = set()
    candidates = sorted([*historical, *delivered], key=lambda r: _date({"published_at": _v(r, "published_at")}) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    for candidate in candidates:
        previous_id = int(_v(candidate, "id") or 0)
        if previous_id in seen:
            continue
        seen.add(previous_id)
        relation = _relation(current, candidate)
        if not relation:
            continue
        known = _v(candidate, "event_id")
        event_id = known if known.startswith("ev25:") else f"ev25:{channel_id}:{previous_id}"
        return EventMatch(relation, previous_id, event_id, "verified source-grounded event identity")
    return EventMatch()


def record_committed_event(store: Any, article_id: int) -> str:
    """Persist the fact snapshot ONLY after a confirmed Telegram COMMITTED receipt."""
    row = store.get_article(int(article_id))
    if row is None or _v(row, "stage") != "PUBLISHED":
        return ""
    channel_id = int(_v(row, "channel_id") or 0)
    if not _delivered(store, channel_id, article_id):
        return ""
    _ensure(store)
    with store.connect() as con:
        saved = con.execute(
            "SELECT event_id FROM event_publication_history WHERE article_id=?", (int(article_id),)
        ).fetchone()
        if saved:
            return str(saved[0])
    match = find_published_event(store, row)
    event_id = match.event_id if match.event_id else f"ev25:{channel_id}:{article_id}"
    facts = _facts(row)
    stamp = _v(row, "published_at") or datetime.now(timezone.utc).isoformat()
    payload = json.dumps(facts or {"family": "unclassified"}, ensure_ascii=False, sort_keys=True)
    now = datetime.now(timezone.utc).isoformat()
    with store.connect() as con:
        con.execute(
            """INSERT INTO event_registry(
                 event_id,channel_id,first_article_id,latest_article_id,event_family,
                 location_key,site_key,latest_facts_json,last_published_at,created_at,updated_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(event_id) DO UPDATE SET
                 latest_article_id=excluded.latest_article_id,
                 latest_facts_json=excluded.latest_facts_json,
                 last_published_at=excluded.last_published_at,
                 updated_at=excluded.updated_at""",
            (event_id,channel_id,match.prior_article_id or article_id,article_id,
             facts.get("family","unclassified"),facts.get("place",""),
             facts.get("target",""),payload,stamp,now,now),
        )
        con.execute(
            """INSERT OR IGNORE INTO event_publication_history(
                 article_id,event_id,channel_id,title,raw_text,source_published_at,
                 published_at,facts_json,committed
               ) VALUES(?,?,?,?,?,?,?,?,1)""",
            (int(article_id),event_id,channel_id,_v(row,"title"),_v(row,"raw_text"),
             _v(row,"source_published_at"),stamp,payload),
        )
    store.update_article(int(article_id), event_key=event_id)
    event("dedupe","2.2.25 committed event snapshot",channel_id=channel_id,
          article_id=int(article_id),event_id=event_id,relation=match.relation)
    return event_id
