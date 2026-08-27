from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from .ai_router import AIRouterError, run_ai
from .database import now_iso
from .secrets_store import load_secrets

LOG = logging.getLogger("telegram_autopilot.rc48")
_INSTALLED = False
_DB_PATCHED = False
_ACTIVE_DB = None

CHECKPOINT_HOURS = (2, 8, 24, 72, 168)
TOP_MEMORY_LIMIT = 30
MIN_MEMORY_POSTS = 10
MAX_PROMPT_EXAMPLES = 4
METRICS_REFRESH_SECONDS = 15 * 60

_WORD_RE = re.compile(r"[0-9A-Za-zА-Яа-яІіЇїЄєҐґ'’-]{3,}", re.U)
_STOPWORDS = {
    "але", "або", "без", "був", "була", "були", "буде", "для", "його", "її", "їх",
    "після", "про", "при", "так", "також", "цей", "ця", "це", "через", "щоб", "який",
    "яка", "які", "the", "and", "for", "from", "with", "that", "this", "was", "were",
    "will", "have", "has", "had", "about", "into", "after", "before",
}


@dataclass(frozen=True, slots=True)
class MemoryExample:
    article_id: int
    title: str
    source_text: str
    final_text: str
    checkpoint_hours: int
    views: int
    forwards: int
    reactions: int
    replies: int
    similarity: float = 0.0


def _row_value(row: Mapping[str, Any] | Any, key: str, default: str = "") -> str:
    try:
        value = row[key]
    except Exception:
        value = getattr(row, key, default)
    return default if value is None else str(value)


def _tokens(value: str) -> set[str]:
    result: set[str] = set()
    for match in _WORD_RE.finditer(str(value or "").casefold().replace("’", "'")):
        token = match.group(0).strip("-'–")
        if len(token) >= 3 and token not in _STOPWORDS:
            result.add(token)
    return result


def _similarity(left: str, right: str) -> float:
    a = _tokens(left)
    b = _tokens(right)
    if not a or not b:
        return 0.0
    overlap = a & b
    jaccard = len(overlap) / max(1, len(a | b))
    containment = len(overlap) / max(1, min(len(a), len(b)))
    number_overlap = sum(1 for token in overlap if any(char.isdigit() for char in token))
    return min(1.0, 0.60 * jaccard + 0.40 * containment + min(0.12, number_overlap * 0.03))


def _parse_dt(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _install_database_patch() -> None:
    global _DB_PATCHED
    if _DB_PATCHED:
        return

    from .database import Database

    original_init = Database._init

    def init_rc48(self):
        original_init(self)
        with self.connect() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS telegram_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
                    article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
                    telegram_message_id TEXT NOT NULL,
                    checkpoint_hours INTEGER NOT NULL,
                    checked_at TEXT NOT NULL,
                    views INTEGER NOT NULL DEFAULT 0,
                    forwards INTEGER NOT NULL DEFAULT 0,
                    reactions INTEGER NOT NULL DEFAULT 0,
                    replies INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(article_id, checkpoint_hours)
                );
                CREATE INDEX IF NOT EXISTS idx_telegram_metrics_channel_checkpoint
                    ON telegram_metrics(channel_id, checkpoint_hours, article_id);
                """
            )

    def metric_candidates(self, channel_id: int, *, limit: int = 40):
        now = datetime.now(timezone.utc)
        with self.connect() as con:
            rows = con.execute(
                """SELECT id,channel_id,title,raw_text,teaser_text,event_summary,published_at,telegram_message_id
                   FROM articles
                   WHERE channel_id=? AND status='published'
                     AND telegram_message_id IS NOT NULL AND telegram_message_id<>''
                     AND published_at IS NOT NULL AND published_at<>''
                   ORDER BY published_at DESC LIMIT 300""",
                (channel_id,),
            ).fetchall()
            existing_rows = con.execute(
                "SELECT article_id,checkpoint_hours FROM telegram_metrics WHERE channel_id=?",
                (channel_id,),
            ).fetchall()
        existing: dict[int, set[int]] = {}
        for row in existing_rows:
            existing.setdefault(int(row["article_id"]), set()).add(int(row["checkpoint_hours"]))

        result: list[dict[str, object]] = []
        for row in rows:
            published = _parse_dt(str(row["published_at"] or ""))
            if published is None:
                continue
            age_hours = (now - published).total_seconds() / 3600.0
            if age_hours < min(CHECKPOINT_HOURS) or age_hours > 240:
                continue
            article_id = int(row["id"])
            missing_due = [
                cp for cp in CHECKPOINT_HOURS
                if age_hours >= cp and cp not in existing.get(article_id, set())
            ]
            if not missing_due:
                continue
            checkpoint = max(missing_due)
            result.append(
                {
                    "article_id": article_id,
                    "channel_id": int(row["channel_id"]),
                    "telegram_message_id": str(row["telegram_message_id"] or ""),
                    "checkpoint_hours": checkpoint,
                    "published_at": str(row["published_at"] or ""),
                    "title": str(row["title"] or ""),
                }
            )
            if len(result) >= max(1, int(limit)):
                break
        return result

    def save_metric(
        self,
        *,
        channel_id: int,
        article_id: int,
        telegram_message_id: str,
        checkpoint_hours: int,
        views: int,
        forwards: int,
        reactions: int,
        replies: int,
    ) -> None:
        with self.connect() as con:
            con.execute(
                """INSERT INTO telegram_metrics(
                       channel_id,article_id,telegram_message_id,checkpoint_hours,checked_at,
                       views,forwards,reactions,replies
                   ) VALUES(?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(article_id,checkpoint_hours) DO UPDATE SET
                       telegram_message_id=excluded.telegram_message_id,
                       checked_at=excluded.checked_at,
                       views=excluded.views,
                       forwards=excluded.forwards,
                       reactions=excluded.reactions,
                       replies=excluded.replies""",
                (
                    int(channel_id), int(article_id), str(telegram_message_id),
                    int(checkpoint_hours), now_iso(),
                    max(0, int(views)), max(0, int(forwards)),
                    max(0, int(reactions)), max(0, int(replies)),
                ),
            )

    def memory_snapshot(self, channel_id: int, *, limit: int = TOP_MEMORY_LIMIT):
        with self.connect() as con:
            counts_rows = con.execute(
                """SELECT checkpoint_hours,COUNT(*) AS n
                   FROM telegram_metrics
                   WHERE channel_id=?
                   GROUP BY checkpoint_hours""",
                (channel_id,),
            ).fetchall()
        counts = {int(row["checkpoint_hours"]): int(row["n"]) for row in counts_rows}

        chosen = 24
        active = False
        for cp in (24, 72, 8, 168, 2):
            if counts.get(cp, 0) >= MIN_MEMORY_POSTS:
                chosen = cp
                active = True
                break
        if not active and counts:
            chosen = max(counts, key=lambda cp: (counts[cp], -abs(cp - 24)))

        with self.connect() as con:
            rows = con.execute(
                """SELECT a.id AS article_id,a.title,a.raw_text,a.teaser_text,a.event_summary,a.published_at,
                          m.checkpoint_hours,m.views,m.forwards,m.reactions,m.replies,m.checked_at
                   FROM telegram_metrics m
                   JOIN articles a ON a.id=m.article_id
                   WHERE m.channel_id=? AND m.checkpoint_hours=?
                     AND a.status='published'
                   ORDER BY (m.reactions + m.forwards + m.replies) DESC,
                            m.forwards DESC,m.views DESC,a.id DESC
                   LIMIT ?""",
                (channel_id, chosen, max(1, min(100, int(limit)))),
            ).fetchall()
        return {
            "active": active,
            "checkpoint_hours": chosen,
            "count": counts.get(chosen, 0),
            "counts": counts,
            "minimum": MIN_MEMORY_POSTS,
            "rows": [dict(row) for row in rows],
        }

    def memory_stats(self, channel_id: int):
        snapshot = memory_snapshot(self, channel_id, limit=TOP_MEMORY_LIMIT)
        with self.connect() as con:
            total = int(con.execute(
                "SELECT COUNT(DISTINCT article_id) FROM telegram_metrics WHERE channel_id=?",
                (channel_id,),
            ).fetchone()[0] or 0)
        return {
            "active": bool(snapshot["active"]),
            "checkpoint_hours": int(snapshot["checkpoint_hours"]),
            "comparable_posts": int(snapshot["count"]),
            "posts_with_metrics": total,
            "top_count": len(snapshot["rows"]),
            "minimum": MIN_MEMORY_POSTS,
            "counts": dict(snapshot["counts"]),
        }

    Database._init = init_rc48
    Database.rc48_metric_candidates = metric_candidates
    Database.rc48_save_metric = save_metric
    Database.rc48_memory_snapshot = memory_snapshot
    Database.rc48_memory_stats = memory_stats
    _DB_PATCHED = True


def _normalize_chat_target_for_mtproto(value: str):
    text = str(value or "").strip()
    if text.startswith("https://t.me/"):
        text = text.split("https://t.me/", 1)[1].split("?", 1)[0].strip("/")
        if "/" in text:
            text = text.split("/", 1)[0]
        return text
    if text.startswith("http://t.me/"):
        text = text.split("http://t.me/", 1)[1].split("?", 1)[0].strip("/")
        if "/" in text:
            text = text.split("/", 1)[0]
        return text
    if text.startswith("@"):
        return text[1:]
    if text.lstrip("-").isdigit():
        try:
            return int(text)
        except ValueError:
            return text
    return text


def authorize_telegram_analytics(
    *,
    api_id: int,
    api_hash: str,
    phone: str,
    existing_session: str = "",
    code_callback,
    password_callback,
) -> tuple[str, str]:
    try:
        from telethon import TelegramClient
        from telethon.errors import SessionPasswordNeededError
        from telethon.sessions import StringSession
    except Exception as exc:
        raise RuntimeError("Не встановлено модуль Telethon для Telegram Analytics.") from exc

    api_id = int(api_id)
    if api_id <= 0 or not str(api_hash).strip():
        raise ValueError("Вкажіть коректні Telegram API ID та API Hash.")
    phone = str(phone or "").strip()
    if not phone:
        raise ValueError("Вкажіть номер телефону Telegram-акаунта.")

    client = TelegramClient(
        StringSession(str(existing_session or "")),
        api_id,
        str(api_hash).strip(),
        connection_retries=1,
        request_retries=1,
        timeout=15,
    )
    try:
        client.connect()
        if not client.is_user_authorized():
            sent = client.send_code_request(phone)
            code = str(code_callback() or "").strip()
            if not code:
                raise RuntimeError("Авторизацію скасовано: код Telegram не введено.")
            try:
                client.sign_in(phone=phone, code=code, phone_code_hash=sent.phone_code_hash)
            except SessionPasswordNeededError:
                password = str(password_callback() or "")
                if not password:
                    raise RuntimeError("Для акаунта увімкнено 2FA, але пароль не введено.")
                client.sign_in(password=password)
        me = client.get_me()
        session = client.session.save()
        display = ""
        if me is not None:
            display = " ".join(
                part for part in (str(getattr(me, "first_name", "") or ""), str(getattr(me, "last_name", "") or ""))
                if part
            ).strip()
            username = str(getattr(me, "username", "") or "").strip()
            if username:
                display = (display + f" (@{username})").strip()
        return str(session or ""), display or "Telegram-акаунт"
    finally:
        client.disconnect()


def _message_metrics(message) -> tuple[int, int, int, int]:
    views = max(0, int(getattr(message, "views", 0) or 0))
    forwards = max(0, int(getattr(message, "forwards", 0) or 0))
    reactions = 0
    reaction_box = getattr(message, "reactions", None)
    for item in (getattr(reaction_box, "results", None) or []):
        reactions += max(0, int(getattr(item, "count", 0) or 0))
    replies_box = getattr(message, "replies", None)
    replies = max(0, int(getattr(replies_box, "replies", 0) or 0))
    return views, forwards, reactions, replies


def refresh_channel_metrics(db, channel, *, force: bool = False) -> dict[str, object]:
    secrets = load_secrets()
    if not (
        int(getattr(secrets, "telegram_api_id", 0) or 0)
        and str(getattr(secrets, "telegram_api_hash", "") or "").strip()
        and str(getattr(secrets, "telegram_user_session", "") or "").strip()
    ):
        return {"configured": False, "checked": 0, "saved": 0, "error": ""}

    rows = db.rc48_metric_candidates(int(channel.id), limit=60 if force else 30)
    if not rows:
        return {"configured": True, "checked": 0, "saved": 0, "error": ""}

    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
    except Exception as exc:
        return {"configured": True, "checked": 0, "saved": 0, "error": f"Telethon: {exc}"}

    target = _normalize_chat_target_for_mtproto(str(getattr(channel, "telegram_chat_id", "") or ""))
    if not target:
        return {"configured": True, "checked": 0, "saved": 0, "error": "Порожній Telegram target каналу."}

    client = TelegramClient(
        StringSession(str(secrets.telegram_user_session)),
        int(secrets.telegram_api_id),
        str(secrets.telegram_api_hash),
        connection_retries=1,
        request_retries=1,
        timeout=12,
    )
    saved = 0
    checked = 0
    try:
        client.connect()
        if not client.is_user_authorized():
            return {"configured": True, "checked": 0, "saved": 0, "error": "Telegram Analytics session не авторизована."}
        entity = client.get_entity(target)
        ids = []
        by_id: dict[int, dict[str, object]] = {}
        for row in rows:
            try:
                message_id = int(str(row["telegram_message_id"]))
            except Exception:
                continue
            ids.append(message_id)
            by_id[message_id] = row
        if not ids:
            return {"configured": True, "checked": 0, "saved": 0, "error": ""}
        messages = client.get_messages(entity, ids=ids)
        if messages is None:
            messages = []
        if not isinstance(messages, (list, tuple)):
            try:
                messages = list(messages)
            except TypeError:
                messages = [messages]
        for message in messages:
            if message is None:
                continue
            message_id = int(getattr(message, "id", 0) or 0)
            row = by_id.get(message_id)
            if row is None:
                continue
            checked += 1
            views, forwards, reactions, replies = _message_metrics(message)
            db.rc48_save_metric(
                channel_id=int(channel.id),
                article_id=int(row["article_id"]),
                telegram_message_id=str(message_id),
                checkpoint_hours=int(row["checkpoint_hours"]),
                views=views,
                forwards=forwards,
                reactions=reactions,
                replies=replies,
            )
            saved += 1
        return {"configured": True, "checked": checked, "saved": saved, "error": ""}
    except Exception as exc:
        return {"configured": True, "checked": checked, "saved": saved, "error": str(exc)[:1000]}
    finally:
        client.disconnect()


def _memory_examples(channel: Any, article: Any, *, limit: int = MAX_PROMPT_EXAMPLES) -> list[MemoryExample]:
    db = _ACTIVE_DB
    if db is None:
        return []
    try:
        snapshot = db.rc48_memory_snapshot(int(getattr(channel, "id", 0) or 0), limit=TOP_MEMORY_LIMIT)
    except Exception:
        return []
    if not snapshot.get("active"):
        return []
    rows = list(snapshot.get("rows") or [])
    if not rows:
        return []

    query = f"{_row_value(article, 'title')}\n{_row_value(article, 'raw_text')}"
    ranked: list[tuple[float, int, dict[str, object]]] = []
    for rank, row in enumerate(rows):
        reference = f"{row.get('title', '')}\n{row.get('raw_text', '')}\n{row.get('event_summary', '')}"
        ranked.append((_similarity(query, reference), rank, row))
    ranked.sort(key=lambda item: (-item[0], item[1]))

    selected = [item for item in ranked if item[0] >= 0.055][: max(1, int(limit))]
    if len(selected) < min(2, int(limit)):
        selected_ids = {int(item[2].get("article_id") or 0) for item in selected}
        for item in ranked:
            article_id = int(item[2].get("article_id") or 0)
            if article_id in selected_ids:
                continue
            selected.append(item)
            selected_ids.add(article_id)
            if len(selected) >= min(2, int(limit)):
                break

    examples: list[MemoryExample] = []
    for similarity, _rank, row in selected[: max(1, int(limit))]:
        final_text = str(row.get("teaser_text") or "").strip()
        if not final_text:
            continue
        examples.append(
            MemoryExample(
                article_id=int(row.get("article_id") or 0),
                title=str(row.get("title") or "").strip(),
                source_text=str(row.get("raw_text") or "").strip(),
                final_text=final_text,
                checkpoint_hours=int(row.get("checkpoint_hours") or 0),
                views=int(row.get("views") or 0),
                forwards=int(row.get("forwards") or 0),
                reactions=int(row.get("reactions") or 0),
                replies=int(row.get("replies") or 0),
                similarity=float(similarity),
            )
        )
    return examples


def _format_memory_block(channel: Any, article: Any, *, purpose: str) -> str:
    examples = _memory_examples(channel, article)
    if not examples:
        return ""

    blocks: list[str] = []
    for index, item in enumerate(examples, start=1):
        post_limit = 420 if purpose == "selection" else 900
        post = " ".join(item.final_text.split())[:post_limit]
        source = " ".join(item.title.split())[:240]
        blocks.append(
            f"ЕТАЛОН {index}\n"
            f"Попередня тема: {source}\n"
            f"Фінальний пост каналу: {post}\n"
            f"Метрики через ~{item.checkpoint_hours} год: "
            f"перегляди {item.views}, реакції {item.reactions}, "
            f"пересилання {item.forwards}, replies {item.replies}."
        )
    guidance = (
        "Це поведінкова редакційна пам'ять ЦЬОГО каналу: попередні пости, які реально "
        "отримали найкращу реакцію аудиторії у порівнюваному часовому вікні. "
        "Використовуй їх лише як м'який орієнтир для вибору кута, щільності, подачі "
        "і того, які деталі цікавлять аудиторію. НЕ копіюй формулювання. "
        "НЕ використовуй жоден факт з еталонів як факт поточної новини. "
        "Профіль каналу, SOURCE та Fact Guard мають вищий пріоритет."
    )
    if purpose == "selection":
        guidance += (
            " Пам'ять не має права протягнути off-profile матеріал лише тому, що схожа "
            "тема колись набрала багато реакцій."
        )
    return guidance + "\n\n" + "\n\n".join(blocks)


def classify_category_rc48(channel: Any, article: Any, categories: list[dict[str, Any]]) -> str:
    if not categories:
        return ""

    from . import rc45_policy as rc45
    from . import rc46_policy as rc46

    lexical = rc45.lexical_category(article, categories)
    if lexical:
        return lexical

    names = "\n".join(f"- {item['name']}" for item in categories)
    profile = " ".join(str(getattr(channel, "editorial_profile", "") or "").split())[:1800]
    memory = _format_memory_block(channel, article, purpose="selection")
    prompt = f"""You are the channel's assignment editor. Classify ONE source item into ONE operator-defined category.
The source may be English, Ukrainian or Russian. Category labels may be in another language; classify by meaning.
A category is valid only when the item also fits the CHANNEL PROFILE as something this channel should publish.
If the item is outside the profile, an evergreen explainer/listicle/review/conference housekeeping item not requested by the profile, or no category genuinely fits, return __OTHER__.
Do not force an item into the nearest category.
Return only one category name or __OTHER__. JSON like {{\"category\":\"...\"}} is accepted.

CHANNEL PROFILE:
{profile or '(not specified)'}

CATEGORIES:
{names}

{memory}

SOURCE TITLE:
{_row_value(article, 'title')[:800]}

SOURCE EXCERPT:
{_row_value(article, 'raw_text')[:2800]}
""".strip()

    def validator(value: str) -> None:
        rc46.extract_category_rc46(value, categories)

    try:
        result = run_ai(
            prompt,
            validator=validator,
            max_output_tokens=64,
            cloud_timeout_seconds=6,
            task_timeout_seconds=12,
            local_repair=False,
            skip_providers={"codex", "local"},
            suppress_provider_on_quota=False,
            allowed_providers={"gemini", "groq", "nvidia", "cloudflare"},
        )
        return rc46.extract_category_rc46(result.text, categories)
    except (AIRouterError, ValueError, TypeError):
        return rc46._UNCLASSIFIED


def install_rc48_learning() -> None:
    global _INSTALLED, _ACTIVE_DB
    if _INSTALLED:
        return

    _install_database_patch()

    from . import production_pipeline as production
    from . import rc40_policy as rc40
    from . import rc47_policy as rc47
    from . import service as service_module
    from .service import AutopilotService

    rc47._CHEAP_CLASSIFIER = classify_category_rc48

    old_trusted_prompt = rc47._trusted_category_prompt
    old_final_prompt = rc47._final_editor_prompt
    old_ru_prompt = rc40.build_russian_editorial_prompt
    old_ua_bridge_prompt = rc40.build_ukrainian_bridge_prompt

    def trusted_prompt_rc48(channel, article, categories):
        base = old_trusted_prompt(channel, article, categories)
        memory = _format_memory_block(channel, article, purpose="selection")
        return base + (("\n\nEDITORIAL LEARNING MEMORY:\n" + memory) if memory else "")

    def final_prompt_rc48(channel, article, draft: str, *, hard_limit: int):
        base = old_final_prompt(channel, article, draft, hard_limit=hard_limit)
        memory = _format_memory_block(channel, article, purpose="writing")
        return base + (("\n\nРЕДАКЦІЙНА ПАМ'ЯТЬ КАНАЛУ:\n" + memory) if memory else "")

    def ru_prompt_rc48(channel, article, *, hard_limit: int):
        base = old_ru_prompt(channel, article, hard_limit=hard_limit)
        memory = _format_memory_block(channel, article, purpose="writing")
        return base + (("\n\nПАМЯТЬ УСПЕШНЫХ ПОСТОВ ЭТОГО КАНАЛА:\n" + memory) if memory else "")

    def ua_bridge_prompt_rc48(channel, article, russian_draft: str, *, hard_limit: int):
        base = old_ua_bridge_prompt(channel, article, russian_draft, hard_limit=hard_limit)
        memory = _format_memory_block(channel, article, purpose="writing")
        return base + (("\n\nРЕДАКЦІЙНА ПАМ'ЯТЬ КАНАЛУ:\n" + memory) if memory else "")

    rc47._trusted_category_prompt = trusted_prompt_rc48
    rc47._final_editor_prompt = final_prompt_rc48
    rc40.build_russian_editorial_prompt = ru_prompt_rc48
    rc40.build_ukrainian_bridge_prompt = ua_bridge_prompt_rc48

    old_service_init = AutopilotService.__init__
    old_run_channel = AutopilotService._run_channel

    def service_init_rc48(self, db, on_event=None):
        global _ACTIVE_DB
        old_service_init(self, db, on_event)
        _ACTIVE_DB = db
        self._rc48_last_metrics_refresh = {}

    def run_channel_rc48(self, channel, *, force: bool):
        last_map = getattr(self, "_rc48_last_metrics_refresh", {})
        now_mono = time.monotonic()
        due = force or now_mono - float(last_map.get(int(channel.id), 0.0)) >= METRICS_REFRESH_SECONDS
        if due:
            try:
                summary = refresh_channel_metrics(self.db, channel, force=force)
                last_map[int(channel.id)] = now_mono
                self._rc48_last_metrics_refresh = last_map
                if summary.get("saved"):
                    self._audit(
                        "editorial_memory", "metrics",
                        f"saved={summary.get('saved')} checked={summary.get('checked')}",
                        channel_id=int(channel.id),
                    )
                    self._emit(
                        "editorial_memory",
                        f"{channel.name}: редакційна пам'ять оновила {summary.get('saved')} метрик",
                    )
                if summary.get("error"):
                    self._audit(
                        "editorial_memory", "degraded", str(summary.get("error"))[:1000],
                        channel_id=int(channel.id),
                    )
            except Exception as exc:
                self.log.debug("RC48 metrics refresh skipped: %s", exc)
        return old_run_channel(self, channel, force=force)

    AutopilotService.__init__ = service_init_rc48
    AutopilotService._run_channel = run_channel_rc48

    production.POST_FORMAT_PREFIX = "telegram-post-v30:"
    service_module.POST_FORMAT_PREFIX = "telegram-post-v30:"

    _INSTALLED = True
