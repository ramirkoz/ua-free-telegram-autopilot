from __future__ import annotations

import logging
import math
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from .database import now_iso
from .models import Decision
from .secrets_store import load_secrets

LOG = logging.getLogger("telegram_autopilot.rc51")
_INSTALLED = False
_DB_PATCHED = False
_ACTIVE_DB = None
_REACTION_POLICY_LAST: dict[int, float] = {}

FEEDBACK_WINDOW_DAYS = 7
METRICS_REFRESH_SECONDS = 15 * 60
LIKE_WEIGHT = 1.0
FIRE_WEIGHT = 2.0
DISLIKE_WEIGHT = -2.0
MAX_FEEDBACK_ROWS = 180
MAX_POSITIVE_EXAMPLES = 4
MAX_NEGATIVE_EXAMPLES = 2

_WORD_RE = re.compile(r"[0-9A-Za-zА-Яа-яІіЇїЄєҐґЁёЫыЭэЪъ'’+-]{3,}", re.U)
_STOPWORDS = {
    "але", "або", "без", "був", "була", "були", "було", "буде", "для", "його", "її", "їх",
    "після", "про", "при", "так", "також", "цей", "ця", "це", "через", "щоб", "який", "яка",
    "які", "новий", "нова", "нове", "the", "and", "for", "from", "with", "that", "this", "was",
    "were", "will", "have", "has", "had", "about", "into", "after", "before", "new", "says", "said",
    "что", "это", "для", "после", "через", "который", "которая", "будет", "также", "или", "при",
}


@dataclass(frozen=True, slots=True)
class FeedbackScore:
    score: float
    positive: float
    negative: float
    hard_suppress: bool
    matched_article_id: int = 0
    matched_similarity: float = 0.0
    matched_age_hours: float = 0.0
    rated_posts: int = 0


def _row_value(row: Mapping[str, Any] | Any, key: str, default: str = "") -> str:
    try:
        value = row[key]
    except Exception:
        value = getattr(row, key, default)
    return default if value is None else str(value)


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


def _tokens(value: str) -> set[str]:
    out: set[str] = set()
    for match in _WORD_RE.finditer(str(value or "").casefold().replace("’", "'")):
        token = match.group(0).strip("-'–+")
        if len(token) < 3 or token in _STOPWORDS:
            continue
        if token.endswith("s") and token.isascii() and len(token) > 5:
            token = token[:-1]
        out.add(token)
    return out


def similarity_parts(left: str, right: str) -> tuple[float, int]:
    a = _tokens(left)
    b = _tokens(right)
    if not a or not b:
        return 0.0, 0
    overlap = a & b
    shared = len(overlap)
    jaccard = shared / max(1, len(a | b))
    containment = shared / max(1, min(len(a), len(b)))
    # Containment matters more for a short incoming headline matching a longer
    # previously published source. Keep the score conservative: one shared brand
    # name must never be enough to suppress a whole subject area.
    return min(1.0, 0.48 * jaccard + 0.52 * containment), shared


def _feedback_signal(row: Mapping[str, Any] | Any) -> float:
    likes = int(_row_value(row, "likes", "0") or 0)
    dislikes = int(_row_value(row, "dislikes", "0") or 0)
    fires = int(_row_value(row, "fires", "0") or 0)
    return likes * LIKE_WEIGHT + fires * FIRE_WEIGHT + dislikes * DISLIKE_WEIGHT


def _candidate_text(article: Mapping[str, Any] | Any) -> str:
    return "\n".join(
        part for part in (
            _row_value(article, "title"),
            _row_value(article, "raw_text")[:6000],
            _row_value(article, "event_summary")[:1200],
        ) if part
    )


def _feedback_text(row: Mapping[str, Any] | Any) -> str:
    return "\n".join(
        part for part in (
            _row_value(row, "title"),
            _row_value(row, "raw_text")[:6000],
            _row_value(row, "event_summary")[:1200],
            _row_value(row, "teaser_text")[:1200],
        ) if part
    )


def score_against_feedback(article: Mapping[str, Any] | Any, feedback_rows: list[Mapping[str, Any] | Any]) -> FeedbackScore:
    query = _candidate_text(article)
    now = datetime.now(timezone.utc)
    positive = 0.0
    negative = 0.0
    hard = False
    matched_id = 0
    matched_sim = 0.0
    matched_age = 0.0
    rated = 0

    for row in feedback_rows:
        signal = _feedback_signal(row)
        if signal == 0:
            continue
        rated += 1
        published = _parse_dt(_row_value(row, "published_at") or _row_value(row, "checked_at"))
        age_hours = 24.0 * FEEDBACK_WINDOW_DAYS
        if published is not None:
            age_hours = max(0.0, (now - published).total_seconds() / 3600.0)
        if age_hours > 24.0 * FEEDBACK_WINDOW_DAYS:
            continue
        sim, shared = similarity_parts(query, _feedback_text(row))
        if sim <= 0:
            continue

        # Three-day half-life makes feedback dynamic. A one-week-old vote still
        # matters, but it cannot become a permanent editorial scar.
        decay = 0.5 ** (age_hours / 72.0)
        contribution = sim * decay * signal
        if contribution >= 0:
            positive += contribution
        else:
            negative += -contribution

        # A dislike is a temporary veto only for genuinely close stories. The
        # similarity threshold rises as the vote gets older so broad subjects do
        # not get banned by one old reaction.
        if signal < 0 and shared >= 4:
            threshold = 0.18 if age_hours <= 24 else 0.24 if age_hours <= 72 else 0.32
            if sim >= threshold:
                hard = True
                if sim > matched_sim:
                    try:
                        matched_id = int(_row_value(row, "article_id", "0") or 0)
                    except Exception:
                        matched_id = 0
                    matched_sim = sim
                    matched_age = age_hours

    return FeedbackScore(
        score=positive - negative,
        positive=positive,
        negative=negative,
        hard_suppress=hard,
        matched_article_id=matched_id,
        matched_similarity=matched_sim,
        matched_age_hours=matched_age,
        rated_posts=rated,
    )


def _reaction_emoji(reaction: Any) -> str:
    value = str(getattr(reaction, "emoticon", "") or "")
    if not value and isinstance(reaction, str):
        value = reaction
    return value.replace("\ufe0f", "").strip()


def reaction_breakdown(message: Any) -> tuple[int, int, int, int, int, int, int]:
    views = max(0, int(getattr(message, "views", 0) or 0))
    forwards = max(0, int(getattr(message, "forwards", 0) or 0))
    replies_box = getattr(message, "replies", None)
    replies = max(0, int(getattr(replies_box, "replies", 0) or 0))
    likes = dislikes = fires = other = 0
    box = getattr(message, "reactions", None)
    for item in (getattr(box, "results", None) or []):
        count = max(0, int(getattr(item, "count", 0) or 0))
        emoji = _reaction_emoji(getattr(item, "reaction", None))
        if emoji == "👍":
            likes += count
        elif emoji == "👎":
            dislikes += count
        elif emoji == "🔥":
            fires += count
        else:
            other += count
    return views, forwards, replies, likes, dislikes, fires, other


def _install_database_patch() -> None:
    global _DB_PATCHED
    if _DB_PATCHED:
        return

    from .database import Database

    original_init = Database._init
    original_history = Database.history
    original_pending = Database.pending_articles

    def init_rc51(self):
        original_init(self)
        with self.connect() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS telegram_feedback (
                    article_id INTEGER PRIMARY KEY REFERENCES articles(id) ON DELETE CASCADE,
                    channel_id INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
                    telegram_message_id TEXT NOT NULL,
                    checked_at TEXT NOT NULL,
                    published_at TEXT NOT NULL DEFAULT '',
                    views INTEGER NOT NULL DEFAULT 0,
                    forwards INTEGER NOT NULL DEFAULT 0,
                    replies INTEGER NOT NULL DEFAULT 0,
                    likes INTEGER NOT NULL DEFAULT 0,
                    dislikes INTEGER NOT NULL DEFAULT 0,
                    fires INTEGER NOT NULL DEFAULT 0,
                    other_reactions INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_telegram_feedback_channel_checked
                    ON telegram_feedback(channel_id, checked_at DESC);
                """
            )
            # RC51 removes manual topic quotas. Keep the legacy column for Data
            # compatibility, but clear its values so old percentages cannot return
            # through a stale UI save or future wrapper.
            columns = {str(row[1]) for row in con.execute("PRAGMA table_info(channels)").fetchall()}
            if "editorial_weights_json" in columns:
                con.execute("UPDATE channels SET editorial_weights_json='[]' WHERE editorial_weights_json<>'[]'")
            # New writer/selection semantics must regenerate any unfinished cached
            # text copied from RC50 instead of silently publishing the old style.
            con.execute(
                """UPDATE articles SET headline_uk='',teaser_text='',full_article_uk='',event_key='',event_summary='',
                          ai_provider='',ai_model='',rewrite_text=''
                   WHERE status IN ('new','retry','processing')"""
            )
            con.execute("DELETE FROM audit_log WHERE datetime(created_at) < datetime('now','-7 days')")
            con.execute("DELETE FROM telegram_feedback WHERE datetime(checked_at) < datetime('now','-8 days')")

    def feedback_candidates(self, channel_id: int, *, limit: int = 120):
        with self.connect() as con:
            rows = con.execute(
                """SELECT id AS article_id,channel_id,telegram_message_id,published_at,title
                   FROM articles
                   WHERE channel_id=? AND status='published'
                     AND telegram_message_id IS NOT NULL AND telegram_message_id<>''
                     AND published_at IS NOT NULL AND published_at<>''
                     AND datetime(published_at) >= datetime('now','-7 days')
                   ORDER BY datetime(published_at) DESC LIMIT ?""",
                (int(channel_id), max(1, min(300, int(limit)))),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_feedback(self, *, channel_id: int, article_id: int, telegram_message_id: str,
                      published_at: str, views: int, forwards: int, replies: int,
                      likes: int, dislikes: int, fires: int, other_reactions: int) -> None:
        with self.connect() as con:
            con.execute(
                """INSERT INTO telegram_feedback(
                       article_id,channel_id,telegram_message_id,checked_at,published_at,
                       views,forwards,replies,likes,dislikes,fires,other_reactions
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(article_id) DO UPDATE SET
                       telegram_message_id=excluded.telegram_message_id,
                       checked_at=excluded.checked_at,published_at=excluded.published_at,
                       views=excluded.views,forwards=excluded.forwards,replies=excluded.replies,
                       likes=excluded.likes,dislikes=excluded.dislikes,fires=excluded.fires,
                       other_reactions=excluded.other_reactions""",
                (
                    int(article_id), int(channel_id), str(telegram_message_id), now_iso(), str(published_at or ""),
                    max(0, int(views)), max(0, int(forwards)), max(0, int(replies)),
                    max(0, int(likes)), max(0, int(dislikes)), max(0, int(fires)), max(0, int(other_reactions)),
                ),
            )

    def feedback_rows(self, channel_id: int, *, days: int = FEEDBACK_WINDOW_DAYS, limit: int = MAX_FEEDBACK_ROWS):
        with self.connect() as con:
            rows = con.execute(
                """SELECT f.*,a.title,a.raw_text,a.event_summary,a.teaser_text
                   FROM telegram_feedback f JOIN articles a ON a.id=f.article_id
                   WHERE f.channel_id=? AND datetime(f.published_at) >= datetime('now', ?)
                     AND (f.likes>0 OR f.dislikes>0 OR f.fires>0)
                   ORDER BY datetime(f.published_at) DESC LIMIT ?""",
                (int(channel_id), f"-{max(1, int(days))} days", max(1, min(500, int(limit)))),
            ).fetchall()
        return [dict(row) for row in rows]

    def feedback_stats(self, channel_id: int):
        with self.connect() as con:
            row = con.execute(
                """SELECT COUNT(*) AS tracked,
                          SUM(CASE WHEN likes>0 OR dislikes>0 OR fires>0 THEN 1 ELSE 0 END) AS rated,
                          COALESCE(SUM(likes),0) AS likes,COALESCE(SUM(dislikes),0) AS dislikes,
                          COALESCE(SUM(fires),0) AS fires
                   FROM telegram_feedback
                   WHERE channel_id=? AND datetime(published_at) >= datetime('now','-7 days')""",
                (int(channel_id),),
            ).fetchone()
        return {
            "tracked": int(row["tracked"] or 0) if row else 0,
            "rated": int(row["rated"] or 0) if row else 0,
            "likes": int(row["likes"] or 0) if row else 0,
            "dislikes": int(row["dislikes"] or 0) if row else 0,
            "fires": int(row["fires"] or 0) if row else 0,
        }

    def history_rc51(self, channel_id: int | None = None, status: str | None = None, limit: int = 500):
        # Operational history is intentionally one week. Published article rows stay
        # in SQLite for exact/event dedupe, so retention does not resurrect duplicates.
        where = ["datetime(COALESCE(NULLIF(a.published_at,''),a.discovered_at)) >= datetime('now','-7 days')"]
        params: list[object] = []
        if channel_id:
            where.append("a.channel_id=?"); params.append(int(channel_id))
        if status:
            where.append("a.status=?"); params.append(str(status))
        clause = " WHERE " + " AND ".join(where)
        with self.connect() as con:
            return con.execute(
                f"""SELECT a.id,c.name channel_name,s.name source_name,a.title,a.headline_uk,a.status,a.reject_reason,a.discovered_at,
                a.published_at,a.ai_provider,a.telegram_message_id,a.telegram_media_count,a.last_error FROM articles a
                JOIN channels c ON c.id=a.channel_id JOIN sources s ON s.id=a.source_id {clause}
                ORDER BY a.id DESC LIMIT ?""",
                tuple(params) + (max(1, min(2000, int(limit))),),
            ).fetchall()

    def pending_rc51(self, channel_id: int, limit: int = 20):
        pool = list(original_pending(self, int(channel_id), limit=max(60, int(limit) * 4)))
        if len(pool) <= 1:
            return pool[:limit]
        try:
            feedback = self.rc51_feedback_rows(int(channel_id), days=FEEDBACK_WINDOW_DAYS, limit=MAX_FEEDBACK_ROWS)
        except Exception:
            feedback = []
        if not feedback:
            return pool[:limit]

        ranked: list[tuple[int, float, int, Any]] = []
        for row in pool:
            verdict = score_against_feedback(row, feedback)
            status_rank = 0 if _row_value(row, "status") == "new" else 1
            try:
                article_id = int(_row_value(row, "id", "0") or 0)
            except Exception:
                article_id = 0
            # Positive affinity raises a story; negative affinity lowers it. Hard
            # suppression is handled in the decision gate rather than silently
            # disappearing from the queue, so its reason remains auditable.
            ranked.append((status_rank, -verdict.score, -article_id, row))
        ranked.sort(key=lambda item: (item[0], item[1], item[2]))
        return [item[3] for item in ranked[: max(1, int(limit))]]

    def set_channel_editorial_weights_rc51(self, channel_id: int, items) -> None:
        with self.connect() as con:
            con.execute(
                "UPDATE channels SET editorial_weights_json='[]',updated_at=datetime('now') WHERE id=?",
                (int(channel_id),),
            )

    Database._init = init_rc51
    Database.rc51_feedback_candidates = feedback_candidates
    Database.rc51_save_feedback = save_feedback
    Database.rc51_feedback_rows = feedback_rows
    Database.rc51_feedback_stats = feedback_stats
    Database.history = history_rc51
    Database.pending_articles = pending_rc51
    Database.set_channel_editorial_weights = set_channel_editorial_weights_rc51
    _DB_PATCHED = True


def _normalize_chat_target(value: str):
    text = str(value or "").strip()
    for prefix in ("https://t.me/", "http://t.me/"):
        if text.startswith(prefix):
            text = text.split(prefix, 1)[1].split("?", 1)[0].strip("/")
            if "/" in text:
                text = text.split("/", 1)[0]
    if text.startswith("@"):
        return text[1:]
    if text.lstrip("-").isdigit():
        try:
            return int(text)
        except ValueError:
            pass
    return text


def _try_limit_channel_reactions(client, entity, channel_id: int) -> str:
    now = time.monotonic()
    if now - float(_REACTION_POLICY_LAST.get(int(channel_id), 0.0)) < 6 * 3600:
        return ""
    _REACTION_POLICY_LAST[int(channel_id)] = now
    try:
        from telethon.tl import functions, types
        available = types.ChatReactionsSome(
            reactions=[
                types.ReactionEmoji(emoticon="👍"),
                types.ReactionEmoji(emoticon="👎"),
                types.ReactionEmoji(emoticon="🔥"),
            ]
        )
        client(functions.messages.SetChatAvailableReactionsRequest(
            peer=entity,
            available_reactions=available,
        ))
        return ""
    except Exception as exc:
        # Reading feedback must keep working even when the connected account is not
        # an admin of a particular channel or Telegram changes this optional API.
        return str(exc)[:500]


def refresh_feedback_metrics(db, channel, *, force: bool = False) -> dict[str, object]:
    secrets = load_secrets()
    if not (
        int(getattr(secrets, "telegram_api_id", 0) or 0)
        and str(getattr(secrets, "telegram_api_hash", "") or "").strip()
        and str(getattr(secrets, "telegram_user_session", "") or "").strip()
    ):
        return {"configured": False, "checked": 0, "saved": 0, "error": "", "policy_warning": ""}

    rows = db.rc51_feedback_candidates(int(channel.id), limit=180 if force else 120)
    if not rows:
        return {"configured": True, "checked": 0, "saved": 0, "error": "", "policy_warning": ""}
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
    except Exception as exc:
        return {"configured": True, "checked": 0, "saved": 0, "error": f"Telethon: {exc}", "policy_warning": ""}

    target = _normalize_chat_target(str(getattr(channel, "telegram_chat_id", "") or ""))
    if not target:
        return {"configured": True, "checked": 0, "saved": 0, "error": "Порожній Telegram target каналу.", "policy_warning": ""}

    client = TelegramClient(
        StringSession(str(secrets.telegram_user_session)),
        int(secrets.telegram_api_id),
        str(secrets.telegram_api_hash),
        connection_retries=1,
        request_retries=1,
        timeout=12,
    )
    saved = checked = 0
    policy_warning = ""
    try:
        client.connect()
        if not client.is_user_authorized():
            return {"configured": True, "checked": 0, "saved": 0, "error": "Telegram Analytics session не авторизована.", "policy_warning": ""}
        entity = client.get_entity(target)
        if force or int(channel.id) not in _REACTION_POLICY_LAST:
            policy_warning = _try_limit_channel_reactions(client, entity, int(channel.id))

        ids: list[int] = []
        by_id: dict[int, dict[str, object]] = {}
        for row in rows:
            try:
                message_id = int(str(row["telegram_message_id"]))
            except Exception:
                continue
            ids.append(message_id)
            by_id[message_id] = row
        messages = client.get_messages(entity, ids=ids) if ids else []
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
            views, forwards, replies, likes, dislikes, fires, other = reaction_breakdown(message)
            db.rc51_save_feedback(
                channel_id=int(channel.id),
                article_id=int(row["article_id"]),
                telegram_message_id=str(message_id),
                published_at=str(row.get("published_at") or ""),
                views=views, forwards=forwards, replies=replies,
                likes=likes, dislikes=dislikes, fires=fires, other_reactions=other,
            )
            saved += 1
        return {
            "configured": True, "checked": checked, "saved": saved,
            "error": "", "policy_warning": policy_warning,
        }
    except Exception as exc:
        return {
            "configured": True, "checked": checked, "saved": saved,
            "error": str(exc)[:1000], "policy_warning": policy_warning,
        }
    finally:
        client.disconnect()


def feedback_memory_block(channel: Any, article: Any, *, purpose: str = "writing") -> str:
    db = _ACTIVE_DB
    if db is None:
        return ""
    try:
        rows = db.rc51_feedback_rows(int(getattr(channel, "id", 0) or 0), days=FEEDBACK_WINDOW_DAYS, limit=MAX_FEEDBACK_ROWS)
    except Exception:
        return ""
    if not rows:
        return ""

    query = _candidate_text(article)
    positives: list[tuple[float, dict[str, Any]]] = []
    negatives: list[tuple[float, dict[str, Any]]] = []
    for row in rows:
        signal = _feedback_signal(row)
        if signal == 0:
            continue
        sim, _shared = similarity_parts(query, _feedback_text(row))
        # Relevance helps choose examples, while the reaction magnitude decides
        # how strongly a post can become an editorial/style reference.
        rank = (0.35 + sim) * abs(signal)
        if signal > 0:
            positives.append((rank, row))
        else:
            negatives.append((rank, row))
    positives.sort(key=lambda item: -item[0])
    negatives.sort(key=lambda item: -item[0])
    positives = positives[:MAX_POSITIVE_EXAMPLES]
    negatives = negatives[:MAX_NEGATIVE_EXAMPLES]
    if not positives and not negatives:
        return ""

    chunks = [
        "ПОВЕДІНКОВА ПАМ'ЯТЬ КАНАЛУ ЗА ОСТАННІ 7 ДНІВ.",
        "Враховуються ТІЛЬКИ 👍, 👎 і 🔥. Відсутність реакції нейтральна. 👍 = позитивний сигнал, 🔥 = сильний позитивний сигнал, 👎 = негативний сигнал.",
        "Реакції підказують тему, кут і стиль, але НЕ є джерелом фактів поточної новини. Факти бери тільки з SOURCE.",
    ]
    if positives:
        chunks.append("\nПОЗИТИВНІ ПРИКЛАДИ. Наслідуй їхню щільність, ритм і спосіб вибору деталей, але не формулювання:")
        for index, (_rank, row) in enumerate(positives, start=1):
            text = " ".join(str(row.get("teaser_text") or "").split())[:850]
            chunks.append(
                f"+{index} 👍{int(row.get('likes') or 0)} 🔥{int(row.get('fires') or 0)} 👎{int(row.get('dislikes') or 0)}: {text}"
            )
    if negatives:
        chunks.append("\nНЕГАТИВНІ ПРИКЛАДИ. Не наслідуй їхній кут, структуру чи суху подачу:")
        for index, (_rank, row) in enumerate(negatives, start=1):
            text = " ".join(str(row.get("teaser_text") or "").split())[:650]
            chunks.append(
                f"-{index} 👍{int(row.get('likes') or 0)} 🔥{int(row.get('fires') or 0)} 👎{int(row.get('dislikes') or 0)}: {text}"
            )
    return "\n".join(chunks)


def build_ru_feedback_editor_prompt(channel: Any, article: Any, *, hard_limit: int) -> str:
    from .evidence_pack import build_evidence_pack

    source = build_evidence_pack(article, char_budget=5400).text
    memory = feedback_memory_block(channel, article, purpose="selection")
    return f"""Ты выпускающий редактор Telegram. Подготовь короткий ВНУТРЕННИЙ план для украинского автора, а не текст сайта и не публикацию.

Выбери ОДНУ конкретную историю из SOURCE. Найди 2–4 факта, которые делают ее живой и понятной, и одну деталь, за которую цепляется внимание, если такая деталь действительно есть в SOURCE. Выбрось справочную шелуху, корпоративные формулировки и перечисление характеристик.

Не выдумывай вывод, мораль, прогноз или 'значение для рынка'. Не добавляй фактов. Не пытайся заполнить лимит. SOURCE — единственный источник фактов.

{memory}

SOURCE TITLE:
{_row_value(article, 'title')[:360]}

SOURCE EVIDENCE PACK:
{source}

Верни только естественный редакторский план на русском, 250–700 знаков.""".strip()


def build_ua_feedback_writer_prompt(channel: Any, article: Any, russian_draft: str, *, hard_limit: int) -> str:
    from .evidence_pack import build_evidence_pack

    source = build_evidence_pack(article, char_budget=5800).text
    memory = feedback_memory_block(channel, article, purpose="writing")
    return f"""Ти пишеш ФІНАЛЬНИЙ пост для Telegram, а не коротку статтю для сайту.

Напиши його з нуля природною сучасною українською. SOURCE EVIDENCE PACK — єдине джерело фактів. Внутрішній редакторський план лише підказує, де історія; він не є доказом і його не треба перекладати.

ЯК МАЄ ЗВУЧАТИ TELEGRAM:
- перше речення одразу дає конкретну подію або найсильніший перевірений факт;
- зазвичай 2–4 короткі абзаци, часто 350–750 символів; коротка сильна історія може бути ще коротшою;
- одна думка на речення, нормальний розмовний ритм без фамільярності;
- залиш одну-дві деталі, які хочеться переказати іншій людині;
- пояснюй тільки те, без чого суть незрозуміла;
- не пиши вступ як для сайту і не завершуй абстрактним 'висновком'.

НЕ ВИКОРИСТОВУЙ ШАБЛОНИ НА КШТАЛТ:
«Для ринку це…», «Цікаво тут…», «Головне тут…», «Це ще один сигнал…», «напрям зрозумілий», «Для маркетингу тут…».
Не будуй кожен пост за схемою «не X, а Y». Не пояснюй читачеві, чому новина 'важлива', якщо це не випливає з конкретного факту.

ФАКТИЧНА БЕЗПЕКА:
- жодного нового факту, числа, дати, сутності, причини, мотиву, оцінки чи прогнозу поза SOURCE;
- зберігай атрибуцію та невизначеність;
- без заголовка, URL, слова «Джерело», хештегів і емодзі;
- заверши повним реченням;
- жорсткий ліміт {int(hard_limit)} символів, але не намагайся його заповнити.

{memory}

SOURCE TITLE:
{_row_value(article, 'title')[:360]}

SOURCE EVIDENCE PACK:
{source}

ВНУТРІШНІЙ ПЛАН (НЕ ДЖЕРЕЛО ФАКТІВ):
{str(russian_draft or '')[:1600]}

Поверни ТІЛЬКИ готовий Telegram-пост.""".strip()


def _feedback_gate(channel: Any, article: Any) -> FeedbackScore:
    db = _ACTIVE_DB
    if db is None:
        return FeedbackScore(0.0, 0.0, 0.0, False)
    try:
        rows = db.rc51_feedback_rows(int(getattr(channel, "id", 0) or 0), days=FEEDBACK_WINDOW_DAYS, limit=MAX_FEEDBACK_ROWS)
    except Exception:
        rows = []
    return score_against_feedback(article, rows)


def install_rc51_feedback() -> None:
    global _INSTALLED, _ACTIVE_DB
    if _INSTALLED:
        return

    _install_database_patch()

    from . import production_pipeline as production
    from . import rc40_policy as rc40
    from . import rc42_policy as rc42
    from . import rc45_policy as rc45
    from . import rc46_policy as rc46
    from . import rc48_learning as rc48
    from . import service as service_module
    from .service import AutopilotService

    # Manual topic buckets are retired. Keep old schema only for backward Data
    # compatibility; no classifier/percentage call participates in publication.
    no_weights = lambda channel: []
    rc42.parse_editorial_weights = no_weights
    rc45.parse_editorial_weights = no_weights
    rc46.parse_editorial_weights = no_weights

    # RC48's service wrapper resolves this module global at runtime. Replacing it
    # upgrades the existing 15-minute scheduler from aggregate metrics to explicit
    # 👍/👎/🔥 feedback without stacking another scheduler thread.
    rc48.refresh_channel_metrics = refresh_feedback_metrics
    rc48._format_memory_block = feedback_memory_block

    rc40.build_russian_editorial_prompt = build_ru_feedback_editor_prompt
    rc40.build_ukrainian_bridge_prompt = build_ua_feedback_writer_prompt

    old_decide = production.decide

    def decide_rc51(channel, article, recent, *, hard_limit=production.MEDIA_POST_HARD_LIMIT, format_marker=None):
        verdict = _feedback_gate(channel, article)
        if verdict.hard_suppress:
            reason = (
                "REACTION_FEEDBACK_RC51_SKIP: схожий матеріал тимчасово приглушено після 👎"
                + (f" на пост #{verdict.matched_article_id}" if verdict.matched_article_id else "")
                + f"; similarity={verdict.matched_similarity:.3f}; age={verdict.matched_age_hours:.1f}h."
            )
            LOG.info(
                "RC51 feedback gate article_id=%s decision=suppress score=%.3f positive=%.3f negative=%.3f %s",
                _row_value(article, "id", "?"), verdict.score, verdict.positive, verdict.negative, reason,
            )
            return Decision(
                decision="reject", duplicate_of=None, reason=reason,
                event_key="reaction-feedback-v1", event_summary=_row_value(article, "title")[:1000],
                headline_uk="", telegram_teaser="", full_article_uk="", media_captions_uk={},
                confidence=0.98, provider="local-rule", model="rc51-reaction-feedback",
            )
        LOG.info(
            "RC51 feedback gate article_id=%s decision=pass score=%.3f positive=%.3f negative=%.3f rated=%s",
            _row_value(article, "id", "?"), verdict.score, verdict.positive, verdict.negative, verdict.rated_posts,
        )
        result = old_decide(channel, article, recent, hard_limit=hard_limit, format_marker=format_marker)
        if result.decision == "publish":
            result.event_key = ("reaction-v1:" + str(result.event_key or ""))[:500]
            result.reason = (
                str(result.reason or "")
                + f" RC51 reaction-memory score={verdict.score:.3f}; manual topic quotas disabled."
            ).strip()
        return result

    production.decide = decide_rc51
    service_module.decide = decide_rc51
    production.POST_FORMAT_PREFIX = "telegram-post-v32:"
    service_module.POST_FORMAT_PREFIX = "telegram-post-v32:"

    old_service_init = AutopilotService.__init__

    def service_init_rc51(self, db, on_event=None):
        global _ACTIVE_DB
        old_service_init(self, db, on_event)
        _ACTIVE_DB = db

    AutopilotService.__init__ = service_init_rc51

    _INSTALLED = True
    LOG.info("RC51 installed: 👍/👎/🔥 feedback ranking, 7-day memory/history, no manual topic quotas")
