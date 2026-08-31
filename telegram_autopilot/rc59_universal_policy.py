from __future__ import annotations

import json
import logging
import re
import statistics
import threading
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Mapping
from tkinter import messagebox, simpledialog, ttk
from tkinter.scrolledtext import ScrolledText

from .models import Decision

LOG = logging.getLogger("telegram_autopilot.rc59")
_INSTALLED = False
_DB_PATCHED = False

POLICY_VERSION = 1
WINDOW_DAYS = 7
MEDIA_REQUIRED = "required"
MEDIA_PREFERRED = "preferred"
MEDIA_OPTIONAL = "optional"
MEDIA_VALUES = (MEDIA_REQUIRED, MEDIA_PREFERRED, MEDIA_OPTIONAL)


@dataclass(slots=True)
class ChannelPolicy:
    channel_id: int = 0
    enabled: bool = True
    purpose: str = ""
    audience: str = "Україномовна аудиторія каналу."
    selection_rules: str = "Обирай матеріали, які прямо відповідають редакційній меті каналу і мають достатньо нової фактичної інформації для самодостатнього Telegram-посту."
    rejection_rules: str = "Відхиляй матеріали, які не відповідають редакційній меті каналу, є дублями, не містять достатньої нової інформації або суперечать явно заданим обмеженням каналу."
    writing_rules: str = "Пиши 2–4 короткі абзаци. Перше речення одразу дає головну подію або найсильніший факт. Одна думка на речення. Не заповнюй ліміт заради довжини."
    style_rules: str = "Природна сучасна українська без канцеляриту, машинних кальок, зайвого жаргону та службових пояснень про роботу AI."
    positive_examples: str = ""
    negative_examples: str = ""
    extra_instructions: str = ""
    selector_extra_prompt: str = ""
    writer_extra_prompt: str = ""
    media_policy: str = MEDIA_REQUIRED
    target_min_chars: int = 300
    target_max_chars: int = 750
    updated_at: str = ""

    @classmethod
    def from_row(cls, row: Mapping[str, Any] | Any) -> "ChannelPolicy":
        def value(key: str, default: Any = "") -> Any:
            try:
                result = row[key]
            except Exception:
                result = getattr(row, key, default)
            return default if result is None else result

        media = str(value("media_policy", MEDIA_REQUIRED) or MEDIA_REQUIRED).strip().casefold()
        if media not in MEDIA_VALUES:
            media = MEDIA_REQUIRED
        return cls(
            channel_id=int(value("channel_id", 0) or 0),
            enabled=bool(int(value("enabled", 1) or 0)),
            purpose=str(value("purpose", "") or ""),
            audience=str(value("audience", "") or ""),
            selection_rules=str(value("selection_rules", "") or ""),
            rejection_rules=str(value("rejection_rules", "") or ""),
            writing_rules=str(value("writing_rules", "") or ""),
            style_rules=str(value("style_rules", "") or ""),
            positive_examples=str(value("positive_examples", "") or ""),
            negative_examples=str(value("negative_examples", "") or ""),
            extra_instructions=str(value("extra_instructions", "") or ""),
            selector_extra_prompt=str(value("selector_extra_prompt", "") or ""),
            writer_extra_prompt=str(value("writer_extra_prompt", "") or ""),
            media_policy=media,
            target_min_chars=max(120, int(value("target_min_chars", 300) or 300)),
            target_max_chars=max(180, int(value("target_max_chars", 750) or 750)),
            updated_at=str(value("updated_at", "") or ""),
        )


def default_policy(channel: Any | None = None) -> ChannelPolicy:
    legacy = " ".join(str(getattr(channel, "editorial_profile", "") or "").split())
    purpose = legacy or "Новинний Telegram-канал із власною редакційною політикою."
    selection = legacy or ChannelPolicy.selection_rules
    return ChannelPolicy(
        channel_id=int(getattr(channel, "id", 0) or 0),
        purpose=purpose,
        selection_rules=selection,
    )


def _clean(value: Any, limit: int = 12000) -> str:
    return str(value or "").strip()[:limit]


def policy_text(policy: ChannelPolicy) -> str:
    return f"""РЕДАКЦІЙНА ПОЛІТИКА КАНАЛУ

МЕТА / ПРО ЩО КАНАЛ:
{_clean(policy.purpose) or 'Не задано.'}

ЦІЛЬОВА АУДИТОРІЯ:
{_clean(policy.audience) or 'Не задано.'}

ЩО ОБИРАТИ:
{_clean(policy.selection_rules) or 'Обирай матеріали, що відповідають меті каналу.'}

ЩО ВІДХИЛЯТИ:
{_clean(policy.rejection_rules) or 'Відхиляй матеріали, що не відповідають меті каналу.'}

ЯК ПИСАТИ:
{_clean(policy.writing_rules) or 'Пиши зрозуміло і стисло.'}

ТОН І СТИЛЬ:
{_clean(policy.style_rules) or 'Природна сучасна українська.'}

ПОЗИТИВНІ РЕДАКЦІЙНІ ПРИКЛАДИ:
{_clean(policy.positive_examples) or 'Не задано.'}

НЕГАТИВНІ РЕДАКЦІЙНІ ПРИКЛАДИ:
{_clean(policy.negative_examples) or 'Не задано.'}

ДОДАТКОВІ ПРАВИЛА:
{_clean(policy.extra_instructions) or 'Немає.'}

МЕДІА-ПОЛІТИКА: {policy.media_policy}
БАЖАНА ДОВЖИНА: {policy.target_min_chars}–{policy.target_max_chars} символів.
""".strip()


def _row_value(row: Mapping[str, Any] | Any, key: str, default: Any = "") -> Any:
    try:
        value = row[key]
    except Exception:
        value = getattr(row, key, default)
    return default if value is None else value


def _parse_dt(value: Any) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _feedback_rows(channel_id: int) -> list[dict[str, Any]]:
    from . import rc51_feedback
    db = rc51_feedback._ACTIVE_DB
    if db is None or not channel_id:
        return []
    try:
        return list(db.rc51_feedback_rows(int(channel_id), days=WINDOW_DAYS, limit=180))
    except Exception:
        return []


def _topic_feedback_signal(row: Mapping[str, Any] | Any) -> float:
    likes = max(0, int(_row_value(row, "likes", 0) or 0))
    dislikes = max(0, int(_row_value(row, "dislikes", 0) or 0))
    return float(likes) - 2.0 * float(dislikes)


def _title_or_summary(row: Mapping[str, Any] | Any) -> str:
    title = " ".join(str(_row_value(row, "title", "") or "").split())
    summary = " ".join(str(_row_value(row, "event_summary", "") or "").split())
    return (title or summary)[:420]


def topic_memory_block(channel_id: int) -> str:
    rows = _feedback_rows(channel_id)
    if not rows:
        return "Ще немає достатньої редакційної пам'яті для цього каналу."

    now = datetime.now(timezone.utc)
    positive: list[tuple[float, str, int, int]] = []
    negative: list[tuple[float, str, int, int]] = []
    audience_rates: list[float] = []

    try:
        from .rc57_feedback_model import audience_raw_rate, audience_performance_score
    except Exception:
        audience_raw_rate = audience_performance_score = None

    for row in rows:
        published = _parse_dt(_row_value(row, "published_at") or _row_value(row, "checked_at"))
        age_hours = 24.0 * WINDOW_DAYS if published is None else max(0.0, (now - published).total_seconds() / 3600.0)
        if age_hours > 24.0 * WINDOW_DAYS:
            continue
        decay = 0.5 ** (age_hours / 96.0)
        signal = _topic_feedback_signal(row)
        label = _title_or_summary(row)
        likes = max(0, int(_row_value(row, "likes", 0) or 0))
        dislikes = max(0, int(_row_value(row, "dislikes", 0) or 0))
        if label and signal > 0:
            positive.append((signal * decay, label, likes, dislikes))
        elif label and signal < 0:
            negative.append((abs(signal) * decay, label, likes, dislikes))
        if audience_raw_rate is not None and int(_row_value(row, "views", 0) or 0) >= 25:
            audience_rates.append(float(audience_raw_rate(row)))

    positive.sort(key=lambda item: -item[0])
    negative.sort(key=lambda item: -item[0])
    chunks = [
        "РЕДАКТОРСЬКА ПАМ'ЯТЬ ТЕМ ЦЬОГО КАНАЛУ ЗА 7 ДНІВ.",
        "👍 і 👎 — тільки тематичний сигнал. 🔥 тут навмисно не враховується: він навчає лише стиль writer-а.",
        "Сигнали адмінів мають пріоритет над аудиторією. Відсутність реакції нейтральна.",
    ]
    if positive:
        chunks.append("\nАДМІНИ ХОЧУТЬ БІЛЬШЕ СХОЖИХ ЗА СЕНСОМ ТЕМ:")
        for _score, label, likes, dislikes in positive[:5]:
            chunks.append(f"+ 👍{likes} 👎{dislikes}: {label}")
    if negative:
        chunks.append("\nАДМІНИ ХОЧУТЬ МЕНШЕ СХОЖИХ ЗА СЕНСОМ ТЕМ:")
        for _score, label, likes, dislikes in negative[:5]:
            chunks.append(f"- 👍{likes} 👎{dislikes}: {label}")

    if audience_performance_score is not None and audience_rates:
        baseline = statistics.median(audience_rates)
        audience: list[tuple[float, str]] = []
        for row in rows:
            if int(_row_value(row, "views", 0) or 0) < 25:
                continue
            label = _title_or_summary(row)
            if not label:
                continue
            perf = float(audience_performance_score(row, baseline))
            if abs(perf) >= 0.15:
                audience.append((perf, label))
        audience.sort(key=lambda item: -item[0])
        top = [item for item in audience if item[0] > 0][:3]
        bottom = [item for item in reversed(audience) if item[0] < 0][:2]
        if top:
            chunks.append("\nМ'ЯКИЙ AUDIENCE SIGNAL, ЯКИЙ МОЖЕ ПІДСИЛИТИ, АЛЕ НЕ ПЕРЕБИТИ РЕДАКТОРА:")
            for perf, label in top:
                chunks.append(f"↗ {perf:+.2f}: {label}")
        if bottom:
            chunks.append("\nАУДИТОРІЯ СЛАБШЕ РЕАГУВАЛА:")
            for perf, label in bottom:
                chunks.append(f"↘ {perf:+.2f}: {label}")
    return "\n".join(chunks)


def generic_learning_summary(channel_id: int) -> str:
    rows = _feedback_rows(channel_id)
    if not rows:
        return "Ще замало реакцій, щоб показати редакційні закономірності."
    positive = negative = fires = 0
    latest = None
    pos_titles: list[str] = []
    neg_titles: list[str] = []
    for row in rows:
        likes = max(0, int(_row_value(row, "likes", 0) or 0))
        dislikes = max(0, int(_row_value(row, "dislikes", 0) or 0))
        fires += max(0, int(_row_value(row, "fires", 0) or 0))
        positive += likes
        negative += dislikes
        label = _title_or_summary(row)
        if label and likes > dislikes and label not in pos_titles:
            pos_titles.append(label)
        if label and dislikes > 0 and label not in neg_titles:
            neg_titles.append(label)
        dt = _parse_dt(_row_value(row, "checked_at") or _row_value(row, "published_at"))
        if dt is not None and (latest is None or dt > latest):
            latest = dt
    lines = [f"EDITOR: 👍 {positive} · 👎 {negative} · 🔥 {fires}"]
    if pos_titles:
        lines.append("↑ Підтримані теми: " + " | ".join(pos_titles[:3]))
    if neg_titles:
        lines.append("↓ Небажані теми: " + " | ".join(neg_titles[:3]))
    if latest is not None:
        lines.append("Останні feedback-дані: " + latest.astimezone().strftime("%d.%m %H:%M"))
    lines.append("👍/👎 навчають відбір тем; 🔥 навчає тільки стиль. Пам'ять ізольована за channel_id.")
    return "\n".join(lines)


def _selector_prompt(policy: ChannelPolicy, article: Any, *, channel_id: int = 0) -> str:
    from .evidence_pack import build_evidence_pack
    source = build_evidence_pack(article, char_budget=5600).text
    memory = topic_memory_block(channel_id)
    return f"""Ти універсальний редакторський SELECTOR Telegram-автопілота.
Ти НЕ знаєш тип каналу за його назвою і НЕ маєш власної тематики. Єдина редакційна політика — CHANNEL POLICY нижче.

Завдання: вирішити, чи цей SOURCE відповідає саме цій політиці.
Не пиши пост. Не рятуй слабку тему красивою подачею. Якщо матеріал прямо підпадає під правила відхилення або не має достатнього fit — reject.
Редакторські 👍/👎 є тематичними прикладами й мають більшу вагу, ніж audience signal. 🔥 у відборі ігноруй.

{policy_text(policy)}

{memory}

ДОДАТКОВА ІНСТРУКЦІЯ SELECTOR-А:
{_clean(policy.selector_extra_prompt) or 'Немає.'}

SOURCE TITLE:
{_clean(_row_value(article, 'title'), 500)}

SOURCE EVIDENCE PACK:
{source}

Поверни ТІЛЬКИ валідний JSON без markdown:
{{"decision":"publish" або "reject","fit_score":0..100,"reason":"коротка конкретна причина українською","angle":"якщо publish — один редакторський кут, якщо reject — порожній рядок","topic_tags":["2–5 коротких змістових тегів"]}}
""".strip()


def _parse_selector(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Selector не повернув JSON.")
    obj = json.loads(text[start : end + 1])
    decision = str(obj.get("decision") or "").strip().casefold()
    if decision not in {"publish", "reject"}:
        raise ValueError("Selector повернув невідоме рішення.")
    fit = max(0, min(100, int(float(obj.get("fit_score", 0) or 0))))
    reason = " ".join(str(obj.get("reason") or "").split())[:500]
    angle = " ".join(str(obj.get("angle") or "").split())[:700]
    tags_raw = obj.get("topic_tags") or []
    if not isinstance(tags_raw, list):
        tags_raw = []
    tags = []
    for item in tags_raw:
        value = " ".join(str(item or "").split())[:80]
        if value and value not in tags:
            tags.append(value)
    if decision == "publish" and fit < 45:
        decision = "reject"
        reason = reason or f"Недостатня відповідність редакційній політиці: {fit}%."
        angle = ""
    if not reason:
        reason = "Відповідність редакційній політиці перевірено."
    return {"decision": decision, "fit_score": fit, "reason": reason, "angle": angle, "topic_tags": tags[:5]}


def _run_selector(policy: ChannelPolicy, article: Any, *, channel_id: int = 0) -> tuple[Any, dict[str, Any]]:
    from .ai_router import run_ai
    prompt = _selector_prompt(policy, article, channel_id=channel_id)

    def validator(raw: str) -> None:
        _parse_selector(raw)

    result = run_ai(
        prompt,
        validator=validator,
        max_output_tokens=320,
        local_prompt=prompt,
        local_max_output_tokens=340,
        cloud_timeout_seconds=24,
        local_timeout_seconds=45,
        task_timeout_seconds=70,
        local_repair=False,
        suppress_provider_on_quota=False,
        allowed_providers={"codex", "gemini", "groq", "nvidia", "cloudflare", "local"},
    )
    return result, _parse_selector(result.text)


def _writer_prompt(policy: ChannelPolicy, channel: Any, article: Any, selector: dict[str, Any], *, hard_limit: int) -> str:
    from .evidence_pack import build_evidence_pack
    from .rc52_feedback import style_memory_block
    source = build_evidence_pack(article, char_budget=6000).text
    style_memory = style_memory_block(channel, article, purpose="writing")
    tags = ", ".join(selector.get("topic_tags") or []) or "не визначено"
    target_max = min(max(policy.target_min_chars, policy.target_max_chars), int(hard_limit))
    return f"""Ти універсальний WRITER Telegram-автопілота.
Ти НЕ визначаєш тематику каналу за назвою. Пиши виключно за CHANNEL POLICY, яку налаштував редактор.
SOURCE EVIDENCE PACK — єдине джерело фактів. Selector дає лише редакторський кут і не є доказом.

{policy_text(policy)}

РЕДАКТОРСЬКИЙ КУТ SELECTOR-А:
{_clean(selector.get('angle')) or 'Візьми найсильнішу перевірену подію із SOURCE.'}

ЗМІСТОВІ ТЕГИ SELECTOR-А: {tags}

{style_memory}

ДОДАТКОВА ІНСТРУКЦІЯ WRITER-А:
{_clean(policy.writer_extra_prompt) or 'Немає.'}

ГЛОБАЛЬНІ НЕЗМІННІ ПРАВИЛА БЕЗПЕКИ:
- факти, числа, дати, назви, причинні зв'язки та атрибуцію бери тільки із SOURCE;
- не вигадуй висновків, мотивів, прогнозів або оцінок;
- не пиши службову відповідь, відмову, пояснення своїх обмежень чи фрази на кшталт «я не можу підготувати пост»;
- якщо матеріал уже дійшов до writer-а, твоє завдання — написати пост за заданим кутом, а не повторно оцінювати відповідність каналу;
- без заголовка, URL, слова «Джерело», хештегів та емодзі;
- закінчи повним реченням;
- бажана довжина {policy.target_min_chars}–{target_max} символів;
- жорсткий ліміт {int(hard_limit)} символів. Не заповнюй його штучно.

SOURCE TITLE:
{_clean(_row_value(article, 'title'), 500)}

SOURCE EVIDENCE PACK:
{source}

Поверни ТІЛЬКИ готовий український Telegram-пост.""".strip()


_REFUSAL_PATTERNS = (
    r"^\s*вибач(?:те)?[,.! ]",
    r"\bя\s+не\s+можу\s+(?:підготувати|написати|створити|зробити)\b",
    r"\bне\s+можу\s+(?:підготувати|написати|створити)\s+пост\b",
    r"\bу\s+(?:наданому|цьому)\s+джерелі\s+немає\b",
    r"\bматеріал\s+не\s+відповідає\s+(?:тематиці|фокусу|політиці)\s+каналу\b",
    r"\bтема\s+не\s+відповідає\s+(?:тематиці|фокусу|політиці)\b",
    r"\bi\s+(?:can'?t|cannot)\s+(?:write|prepare|create)\b",
    r"\bне\s+могу\s+(?:подготовить|написать|создать)\b",
)


def refusal_meta_reason(text: str) -> str:
    value = " ".join(str(text or "").split()).casefold()
    for pattern in _REFUSAL_PATTERNS:
        if re.search(pattern, value, re.I):
            return "AI повернув службову відмову/метакоментар замість публікації."
    return ""


def score_against_feedback_rc59(article: Any, feedback_rows: list[Any]):
    from . import rc51_feedback as rc51
    from .rc57_feedback_model import AUDIENCE_TOPIC_WEIGHT, SOURCE_AUDIENCE_WEIGHT, audience_performance_score, audience_raw_rate

    query = rc51._candidate_text(article)
    now = datetime.now(timezone.utc)
    positive = negative = 0.0
    hard = False
    matched_id = 0
    matched_sim = 0.0
    matched_age = 0.0
    rated = 0
    rates = [audience_raw_rate(row) for row in feedback_rows if int(_row_value(row, "views", 0) or 0) >= 25]
    baseline = statistics.median(rates) if rates else 0.0
    candidate_source_id = str(_row_value(article, "source_id", "") or "")
    source_scores: list[float] = []

    for row in feedback_rows:
        published = rc51._parse_dt(str(_row_value(row, "published_at", "") or _row_value(row, "checked_at", "")))
        age_hours = 24.0 * WINDOW_DAYS if published is None else max(0.0, (now - published).total_seconds() / 3600.0)
        if age_hours > 24.0 * WINDOW_DAYS:
            continue
        decay = 0.5 ** (age_hours / 96.0)
        sim, shared = rc51.similarity_parts(query, rc51._feedback_text(row))
        editor_signal = _topic_feedback_signal(row)
        if editor_signal != 0:
            rated += 1
            contribution = sim * decay * editor_signal
            if contribution >= 0:
                positive += contribution
            else:
                negative += -contribution
            if editor_signal < 0 and shared >= 4 and sim >= (0.20 if age_hours <= 24 else 0.27 if age_hours <= 72 else 0.34):
                hard = True
                if sim > matched_sim:
                    matched_sim = sim
                    matched_age = age_hours
                    try:
                        matched_id = int(_row_value(row, "article_id", 0) or 0)
                    except Exception:
                        matched_id = 0

        if int(_row_value(row, "views", 0) or 0) >= 25:
            perf = audience_performance_score(row, baseline)
            audience_contribution = sim * decay * perf * AUDIENCE_TOPIC_WEIGHT
            if audience_contribution >= 0:
                positive += audience_contribution
            else:
                negative += -audience_contribution
            if candidate_source_id and str(_row_value(row, "source_id", "") or "") == candidate_source_id:
                source_scores.append(perf * decay)

    if source_scores:
        source_bonus = max(-SOURCE_AUDIENCE_WEIGHT, min(SOURCE_AUDIENCE_WEIGHT * 2, statistics.mean(source_scores) * SOURCE_AUDIENCE_WEIGHT))
        if source_bonus >= 0:
            positive += source_bonus
        else:
            negative += -source_bonus

    return rc51.FeedbackScore(
        score=positive - negative,
        positive=positive,
        negative=negative,
        hard_suppress=hard,
        matched_article_id=matched_id,
        matched_similarity=matched_sim,
        matched_age_hours=matched_age,
        rated_posts=rated,
    )


def _install_database_patch() -> None:
    global _DB_PATCHED
    if _DB_PATCHED:
        return
    from .database import Database, now_iso
    previous_init = Database._init

    def init_rc59(self):
        previous_init(self)
        with self.connect() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS channel_policies (
                    channel_id INTEGER PRIMARY KEY REFERENCES channels(id) ON DELETE CASCADE,
                    policy_version INTEGER NOT NULL DEFAULT 1,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    purpose TEXT NOT NULL DEFAULT '',
                    audience TEXT NOT NULL DEFAULT '',
                    selection_rules TEXT NOT NULL DEFAULT '',
                    rejection_rules TEXT NOT NULL DEFAULT '',
                    writing_rules TEXT NOT NULL DEFAULT '',
                    style_rules TEXT NOT NULL DEFAULT '',
                    positive_examples TEXT NOT NULL DEFAULT '',
                    negative_examples TEXT NOT NULL DEFAULT '',
                    extra_instructions TEXT NOT NULL DEFAULT '',
                    selector_extra_prompt TEXT NOT NULL DEFAULT '',
                    writer_extra_prompt TEXT NOT NULL DEFAULT '',
                    media_policy TEXT NOT NULL DEFAULT 'required',
                    target_min_chars INTEGER NOT NULL DEFAULT 300,
                    target_max_chars INTEGER NOT NULL DEFAULT 750,
                    updated_at TEXT NOT NULL
                );
                """
            )
            rows = con.execute(
                """SELECT c.id,c.editorial_profile FROM channels c
                   LEFT JOIN channel_policies p ON p.channel_id=c.id
                   WHERE p.channel_id IS NULL"""
            ).fetchall()
            for row in rows:
                legacy = " ".join(str(row["editorial_profile"] or "").split())
                fallback = default_policy(SimpleNamespace(id=int(row["id"]), editorial_profile=legacy))
                con.execute(
                    """INSERT INTO channel_policies(
                           channel_id,policy_version,enabled,purpose,audience,selection_rules,rejection_rules,
                           writing_rules,style_rules,positive_examples,negative_examples,extra_instructions,
                           selector_extra_prompt,writer_extra_prompt,media_policy,target_min_chars,target_max_chars,updated_at
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        int(row["id"]), POLICY_VERSION, 1, fallback.purpose, fallback.audience,
                        fallback.selection_rules, fallback.rejection_rules, fallback.writing_rules,
                        fallback.style_rules, "", "", "", "", "", fallback.media_policy,
                        fallback.target_min_chars, fallback.target_max_chars, now_iso(),
                    ),
                )
            con.execute(
                """UPDATE articles SET headline_uk='',teaser_text='',full_article_uk='',event_key='',event_summary='',
                          ai_provider='',ai_model='',rewrite_text=''
                   WHERE status IN ('new','retry','processing')"""
            )

    def get_policy(self, channel_id: int) -> ChannelPolicy:
        with self.connect() as con:
            row = con.execute("SELECT * FROM channel_policies WHERE channel_id=?", (int(channel_id),)).fetchone()
        if row:
            return ChannelPolicy.from_row(row)
        channel = self.get_channel(int(channel_id))
        return default_policy(channel)

    def save_policy(self, policy: ChannelPolicy) -> None:
        media = policy.media_policy if policy.media_policy in MEDIA_VALUES else MEDIA_REQUIRED
        minimum = max(120, min(4000, int(policy.target_min_chars)))
        maximum = max(minimum, min(4096, int(policy.target_max_chars)))
        stamp = now_iso()
        with self.connect() as con:
            con.execute(
                """INSERT INTO channel_policies(
                       channel_id,policy_version,enabled,purpose,audience,selection_rules,rejection_rules,
                       writing_rules,style_rules,positive_examples,negative_examples,extra_instructions,
                       selector_extra_prompt,writer_extra_prompt,media_policy,target_min_chars,target_max_chars,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(channel_id) DO UPDATE SET
                       policy_version=excluded.policy_version,enabled=excluded.enabled,purpose=excluded.purpose,
                       audience=excluded.audience,selection_rules=excluded.selection_rules,rejection_rules=excluded.rejection_rules,
                       writing_rules=excluded.writing_rules,style_rules=excluded.style_rules,
                       positive_examples=excluded.positive_examples,negative_examples=excluded.negative_examples,
                       extra_instructions=excluded.extra_instructions,selector_extra_prompt=excluded.selector_extra_prompt,
                       writer_extra_prompt=excluded.writer_extra_prompt,media_policy=excluded.media_policy,
                       target_min_chars=excluded.target_min_chars,target_max_chars=excluded.target_max_chars,
                       updated_at=excluded.updated_at""",
                (
                    int(policy.channel_id), POLICY_VERSION, int(policy.enabled), _clean(policy.purpose),
                    _clean(policy.audience), _clean(policy.selection_rules), _clean(policy.rejection_rules),
                    _clean(policy.writing_rules), _clean(policy.style_rules), _clean(policy.positive_examples),
                    _clean(policy.negative_examples), _clean(policy.extra_instructions),
                    _clean(policy.selector_extra_prompt), _clean(policy.writer_extra_prompt), media,
                    minimum, maximum, stamp,
                ),
            )

    Database._init = init_rc59
    Database.rc59_get_channel_policy = get_policy
    Database.rc59_save_channel_policy = save_policy
    _DB_PATCHED = True


def _reject(article: Any, reason: str, *, event_key: str, model: str, confidence: float = 0.99) -> Decision:
    return Decision(
        decision="reject", duplicate_of=None, reason=reason,
        event_key=event_key, event_summary=str(_row_value(article, "title", "") or "")[:1000],
        headline_uk="", telegram_teaser="", full_article_uk="", media_captions_uk={},
        confidence=confidence, provider="local-rule", model=model,
    )


def decide_rc59(channel: Any, article: Any, recent: list[Any], *, hard_limit: int, format_marker: str | None = None) -> Decision:
    from . import production_pipeline as production
    from . import rc40_policy as rc40
    from . import rc51_feedback as rc51
    from .ai_router import AIRouterError
    from .rc39_policy import anti_slop_issues

    db = rc51._ACTIVE_DB
    policy = db.rc59_get_channel_policy(int(channel.id)) if db is not None else default_policy(channel)
    article_id = _row_value(article, "id", "?")
    LOG.info("RC59 stage article_id=%s channel_id=%s stage=START", article_id, getattr(channel, "id", 0))

    if not policy.enabled:
        return _reject(article, "CHANNEL_POLICY_DISABLED: редакційна політика цього каналу вимкнена.", event_key="rc59-policy-disabled", model="rc59-policy")
    if not _clean(policy.purpose) or not _clean(policy.selection_rules):
        return _reject(article, "CHANNEL_POLICY_INCOMPLETE: заповніть мету каналу та правила відбору в налаштуваннях.", event_key="rc59-policy-incomplete", model="rc59-policy")
    if policy.media_policy == MEDIA_REQUIRED and int(hard_limit) > int(production.MEDIA_POST_HARD_LIMIT):
        return _reject(article, "SKIP_NO_MEDIA: політика каналу вимагає релевантне фото або відео.", event_key="rc59-media-required", model="rc59-media-policy")

    duplicate_id = production._title_duplicate(article, recent)
    if duplicate_id is not None:
        return Decision(
            decision="duplicate", duplicate_of=duplicate_id,
            reason=f"Дуже близький заголовок до вже опублікованого матеріалу #{duplicate_id}.",
            event_key="title-duplicate", event_summary=str(_row_value(article, "title", "") or "")[:1000],
            headline_uk="", telegram_teaser="", full_article_uk="", media_captions_uk={},
            confidence=0.99, provider="local-rule", model="title-dedupe",
        )

    feedback_rows = _feedback_rows(int(channel.id))
    verdict = score_against_feedback_rc59(article, feedback_rows)
    if verdict.hard_suppress:
        return _reject(
            article,
            "REACTION_FEEDBACK_RC59_SKIP: дуже схожу тему тимчасово приглушено після редакторського 👎. "
            f"similarity={verdict.matched_similarity:.3f}; age={verdict.matched_age_hours:.1f}h.",
            event_key="rc59-reaction-suppress", model="rc59-reaction-feedback", confidence=0.98,
        )

    try:
        selector_result, selector = _run_selector(policy, article, channel_id=int(channel.id))
    except Exception as exc:
        LOG.warning("RC59 selector failed article_id=%s error=%s", article_id, exc)
        return _reject(
            article,
            "SELECTOR_UNAVAILABLE: редакційний selector не дав валідного рішення; матеріал не публікується без перевірки. " + str(exc)[:350],
            event_key="rc59-selector-unavailable", model="rc59-selector-safe-fail", confidence=1.0,
        )

    if selector["decision"] != "publish":
        return _reject(
            article,
            f"CHANNEL_POLICY_REJECT fit={selector['fit_score']}%: {selector['reason']}",
            event_key="rc59-channel-policy-reject", model=f"rc59-selector/{selector_result.provider}", confidence=0.96,
        )

    allowed_years = rc40._rc40_allowed_years(article)
    allowed_numbers = rc40._rc40_allowed_numbers(article)
    prompt = _writer_prompt(policy, channel, article, selector, hard_limit=hard_limit)

    def hard_validator(raw: str) -> None:
        body = rc40._validated_ua_body(
            raw, article=article, allowed_years=allowed_years,
            allowed_numbers=allowed_numbers, hard_limit=hard_limit,
        )
        meta = refusal_meta_reason(body)
        if meta:
            raise production.ProductionPipelineError(meta)

    LOG.info("RC59 stage article_id=%s stage=WRITER_START fit=%s", article_id, selector["fit_score"])
    try:
        final_result = production.run_ai(
            prompt, validator=hard_validator,
            max_output_tokens=620, local_prompt=prompt, local_max_output_tokens=620,
            cloud_timeout_seconds=32, local_timeout_seconds=20, task_timeout_seconds=90,
            local_repair=False, suppress_provider_on_quota=False,
            allowed_providers={"codex", "gemini"},
        )
    except AIRouterError as primary_exc:
        try:
            final_result = production.run_ai(
                prompt, validator=hard_validator,
                max_output_tokens=620, local_prompt=prompt, local_max_output_tokens=620,
                cloud_timeout_seconds=24, local_timeout_seconds=20, task_timeout_seconds=75,
                local_repair=False, suppress_provider_on_quota=False,
                allowed_providers={"groq", "nvidia", "cloudflare", "local"},
            )
        except Exception as fallback_exc:
            raise production.PostAIQAExhausted(
                "RC59: жоден writer не дав фактично безпечний пост. " + str(fallback_exc),
                (str(primary_exc), str(fallback_exc)),
                provider_outage="Немає доступного AI-провайдера" in str(fallback_exc),
            ) from fallback_exc

    body = rc40._validated_ua_body(
        final_result.text, article=article, allowed_years=allowed_years,
        allowed_numbers=allowed_numbers, hard_limit=hard_limit,
    )
    meta = refusal_meta_reason(body)
    if meta:
        raise production.PostAIQAExhausted(meta, (meta,), provider_outage=False)

    quality = production.assess_rewrite(body, hard_limit=hard_limit)
    slop = anti_slop_issues(body)
    soft_issues = tuple(dict.fromkeys(tuple(quality.issues) + tuple(slop)))
    if quality.score < 82 or slop:
        repair = rc40._repair_prompt(prompt, body, soft_issues, quality.score)
        try:
            repair_result = production.run_ai(
                repair, validator=hard_validator,
                max_output_tokens=620, local_prompt=repair, local_max_output_tokens=620,
                cloud_timeout_seconds=28, local_timeout_seconds=15, task_timeout_seconds=55,
                local_repair=False, suppress_provider_on_quota=False,
                allowed_providers={final_result.provider},
            )
            repaired = rc40._validated_ua_body(
                repair_result.text, article=article, allowed_years=allowed_years,
                allowed_numbers=allowed_numbers, hard_limit=hard_limit,
            )
            if not refusal_meta_reason(repaired):
                repaired_quality = production.assess_rewrite(repaired, hard_limit=hard_limit)
                repaired_slop = anti_slop_issues(repaired)
                if (repaired_quality.score, -len(repaired_slop)) > (quality.score, -len(slop)):
                    body, quality, slop, final_result = repaired, repaired_quality, repaired_slop, repair_result
        except Exception as exc:
            LOG.warning("RC59 targeted repair skipped article_id=%s error=%s", article_id, exc)

    lt_result = production.apply_local_languagetool_detailed(body, timeout=1.8, max_changes=24, require_ready=False)
    polished = production.apply_safe_ukrainian_fixes(lt_result.text)
    if polished != body:
        try:
            checked = rc40._validated_ua_body(
                polished, article=article, allowed_years=allowed_years,
                allowed_numbers=allowed_numbers, hard_limit=hard_limit,
            )
            if not refusal_meta_reason(checked):
                body = checked
        except Exception:
            pass

    body = rc40._validated_ua_body(
        body, article=article, allowed_years=allowed_years,
        allowed_numbers=allowed_numbers, hard_limit=hard_limit,
    )
    meta = refusal_meta_reason(body)
    if meta:
        raise production.PostAIQAExhausted(meta, (meta,), provider_outage=False)

    title_key = " ".join(sorted(production._norm_words(str(_row_value(article, "title", "") or ""))))[:430] or "news"
    marker = format_marker or f"telegram-post-v36:{hard_limit}:"
    tags = ",".join(selector.get("topic_tags") or [])[:240]
    reason = (
        f"RC59 universal policy PASS; fit={selector['fit_score']}%; selector={selector_result.provider}/{selector_result.model}; "
        f"writer={final_result.provider}/{final_result.model}; reaction_score={verdict.score:.3f}; tags={tags or 'none'}; "
        "global Fact/Language/Refusal QA PASS."
    )
    LOG.info("RC59 publish-ready article_id=%s fit=%s writer=%s/%s", article_id, selector["fit_score"], final_result.provider, final_result.model)
    return Decision(
        decision="publish", duplicate_of=None, reason=reason,
        event_key=(marker + title_key)[:500], event_summary=body[:1000],
        headline_uk=production.BODY_ONLY_SENTINEL, telegram_teaser=body, full_article_uk=body,
        media_captions_uk={}, confidence=min(0.99, 0.72 + selector["fit_score"] / 400.0),
        provider=final_result.provider, model=final_result.model,
    )


def _install_ui() -> None:
    from .ui import MainWindow
    from .secrets_store import load_secrets, save_secrets
    from .telegram import normalize_chat_target, test_bot

    def channel_dialog_rc59(self, ch):
        win = tk.Toplevel(self.root)
        win.title("Канал · редакційна політика")
        win.transient(self.root)
        win.grab_set()
        win.geometry("1080x800")
        win.minsize(900, 700)

        policy = self.db.rc59_get_channel_policy(int(ch.id)) if ch else default_policy(None)
        tabs = ttk.Notebook(win)
        tabs.pack(fill="both", expand=True, padx=10, pady=10)
        basic = ttk.Frame(tabs, padding=12)
        mission = ttk.Frame(tabs, padding=12)
        selection = ttk.Frame(tabs, padding=12)
        writing = ttk.Frame(tabs, padding=12)
        examples = ttk.Frame(tabs, padding=12)
        advanced = ttk.Frame(tabs, padding=12)
        tabs.add(basic, text="Основне")
        tabs.add(mission, text="Місія")
        tabs.add(selection, text="Відбір")
        tabs.add(writing, text="Написання")
        tabs.add(examples, text="Приклади")
        tabs.add(advanced, text="Розширене")

        fields: dict[str, Any] = {}

        def entry(parent, label, value="", show=""):
            frame = ttk.Frame(parent)
            frame.pack(fill="x", pady=5)
            ttk.Label(frame, text=label, width=34).pack(side="left")
            widget = ttk.Entry(frame, show=show)
            widget.pack(side="left", fill="x", expand=True)
            widget.insert(0, str(value))
            return widget

        def text_box(parent, label, value="", height=7, hint=""):
            ttk.Label(parent, text=label, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(6, 2))
            if hint:
                ttk.Label(parent, text=hint, foreground="#666", wraplength=980).pack(anchor="w", pady=(0, 3))
            widget = ScrolledText(parent, height=height, wrap="word", undo=True)
            widget.pack(fill="both", expand=True, pady=(0, 8))
            widget.insert("1.0", str(value or ""))
            return widget

        fields["name"] = entry(basic, "Назва каналу", ch.name if ch else "")
        fields["chat"] = entry(basic, "Telegram: посилання / @username / Chat ID", ch.telegram_chat_id if ch else "")
        secret = load_secrets()
        existing = secret.channel_bot_tokens.get(str(ch.id), "") if ch else ""
        fields["token"] = entry(basic, "Bot Token (необов'язково)", existing, show="•")
        nums = ttk.LabelFrame(basic, text="Автоматизація", padding=10)
        nums.pack(fill="x", pady=10)
        values = [
            ("poll", "Перевірка джерел, хв", ch.poll_interval_minutes if ch else 5),
            ("gap", "Мін. пауза між постами, хв", ch.min_publish_interval_minutes if ch else 10),
            ("dedupe", "Вікно дедуплікації, год", ch.dedupe_window_hours if ch else 72),
            ("age", "Макс. вік матеріалу, год", ch.max_age_hours if ch else 24),
            ("maxcycle", "Макс. постів за цикл", ch.max_posts_per_cycle if ch else 3),
        ]
        for row, (key, label, value) in enumerate(values):
            ttk.Label(nums, text=label).grid(row=row, column=0, sticky="w", pady=4)
            widget = ttk.Entry(nums, width=12)
            widget.insert(0, str(value))
            widget.grid(row=row, column=1, sticky="w", padx=8)
            fields[key] = widget
        enabled = tk.BooleanVar(value=ch.enabled if ch else True)
        ttk.Checkbutton(nums, text="Канал активний", variable=enabled).grid(row=0, column=2, sticky="w", padx=22)

        fields["purpose"] = text_box(mission, "Про що канал / його місія", policy.purpose, 9, "Саме це, а не назва каналу, визначає редакційний напрям.")
        fields["audience"] = text_box(mission, "Для кого пишемо", policy.audience, 8, "Опиши читача: рівень підготовки, інтереси, очікувану складність.")

        fields["selection_rules"] = text_box(selection, "Що шукати і пропускати", policy.selection_rules, 10, "Критерії хорошого кандидата. Можна писати природною мовою, списком або прикладами.")
        fields["rejection_rules"] = text_box(selection, "Що відхиляти", policy.rejection_rules, 9, "Hard exclusions і небажані типи матеріалів.")
        media_frame = ttk.Frame(selection)
        media_frame.pack(fill="x", pady=6)
        ttk.Label(media_frame, text="Медіа-політика", width=24).pack(side="left")
        media_var = tk.StringVar(value=policy.media_policy)
        media_combo = ttk.Combobox(media_frame, textvariable=media_var, state="readonly", values=MEDIA_VALUES, width=18)
        media_combo.pack(side="left")
        ttk.Label(media_frame, text="required = без медіа не публікувати · preferred = бажано · optional = не вимагати", foreground="#666").pack(side="left", padx=12)

        fields["writing_rules"] = text_box(writing, "Структура і спосіб написання", policy.writing_rules, 9)
        fields["style_rules"] = text_box(writing, "Тон і стиль", policy.style_rules, 9)
        length_frame = ttk.Frame(writing)
        length_frame.pack(fill="x", pady=6)
        ttk.Label(length_frame, text="Бажана довжина, символів").pack(side="left")
        fields["target_min"] = ttk.Entry(length_frame, width=8)
        fields["target_min"].insert(0, str(policy.target_min_chars))
        fields["target_min"].pack(side="left", padx=(10, 4))
        ttk.Label(length_frame, text="–").pack(side="left")
        fields["target_max"] = ttk.Entry(length_frame, width=8)
        fields["target_max"].insert(0, str(policy.target_max_chars))
        fields["target_max"].pack(side="left", padx=4)

        fields["positive_examples"] = text_box(examples, "Хороші теми / кейси", policy.positive_examples, 10, "Ручні приклади редактора. Реакції 👍 доповнюють їх автоматично.")
        fields["negative_examples"] = text_box(examples, "Небажані теми / кейси", policy.negative_examples, 10, "Ручні негативні приклади. Реакції 👎 доповнюють їх автоматично.")

        fields["extra_instructions"] = text_box(advanced, "Додаткові редакційні правила", policy.extra_instructions, 6)
        fields["selector_extra_prompt"] = text_box(advanced, "Додатковий prompt selector-а", policy.selector_extra_prompt, 6, "Використовуй лише для специфічних правил відбору, які не помістилися вище.")
        fields["writer_extra_prompt"] = text_box(advanced, "Додатковий prompt writer-а", policy.writer_extra_prompt, 6, "Використовуй лише для специфічних правил написання.")
        policy_enabled = tk.BooleanVar(value=policy.enabled)
        ttk.Checkbutton(advanced, text="Редакційна політика активна", variable=policy_enabled).pack(anchor="w", pady=6)

        def text_value(key: str) -> str:
            widget = fields[key]
            return widget.get("1.0", "end-1c").strip()

        def current_policy(channel_id: int = 0) -> ChannelPolicy:
            return ChannelPolicy(
                channel_id=channel_id,
                enabled=policy_enabled.get(),
                purpose=text_value("purpose"),
                audience=text_value("audience"),
                selection_rules=text_value("selection_rules"),
                rejection_rules=text_value("rejection_rules"),
                writing_rules=text_value("writing_rules"),
                style_rules=text_value("style_rules"),
                positive_examples=text_value("positive_examples"),
                negative_examples=text_value("negative_examples"),
                extra_instructions=text_value("extra_instructions"),
                selector_extra_prompt=text_value("selector_extra_prompt"),
                writer_extra_prompt=text_value("writer_extra_prompt"),
                media_policy=media_var.get(),
                target_min_chars=int(fields["target_min"].get()),
                target_max_chars=int(fields["target_max"].get()),
            )

        def show_prompt():
            try:
                p = current_policy(int(ch.id) if ch else 0)
                preview = tk.Toplevel(win)
                preview.title("Фактична редакційна інструкція AI")
                preview.geometry("980x760")
                text = ScrolledText(preview, wrap="word")
                text.pack(fill="both", expand=True, padx=10, pady=10)
                text.insert("1.0", policy_text(p) + "\n\n--- SELECTOR TEMPLATE ---\n\n" + _selector_prompt(p, {"title": "<TITLE>", "raw_text": "<SOURCE>"}, channel_id=int(ch.id) if ch else 0) + "\n\n--- WRITER TEMPLATE ---\n\n" + _writer_prompt(p, SimpleNamespace(id=int(ch.id) if ch else 0), {"title": "<TITLE>", "raw_text": "<SOURCE>"}, {"angle": "<ANGLE>", "topic_tags": ["<TAG>"], "fit_score": 80}, hard_limit=900))
                text.configure(state="disabled")
            except Exception as exc:
                messagebox.showerror("UA FREE Telegram Autopilot", str(exc), parent=win)

        def test_policy():
            try:
                p = current_policy(int(ch.id) if ch else 0)
            except Exception as exc:
                messagebox.showerror("UA FREE Telegram Autopilot", str(exc), parent=win)
                return
            title = simpledialog.askstring("Тест політики", "Заголовок тестового матеріалу:", parent=win)
            if title is None:
                return
            source = simpledialog.askstring("Тест політики", "Короткий текст / опис джерела:", parent=win)
            if source is None:
                return
            status = messagebox.showinfo("Тест політики", "Запускаю selector. Результат з'явиться окремим повідомленням.", parent=win)

            def work():
                try:
                    result, verdict = _run_selector(p, {"title": title, "raw_text": source}, channel_id=int(ch.id) if ch else 0)
                    detail = f"Рішення: {verdict['decision'].upper()}\nFit: {verdict['fit_score']}%\nПричина: {verdict['reason']}\nКут: {verdict['angle'] or '—'}\nТеги: {', '.join(verdict['topic_tags']) or '—'}\nAI: {result.provider}/{result.model}"
                    self._post_ui(messagebox.showinfo, "Тест політики", detail, parent=win)
                except Exception as exc:
                    self._post_ui(messagebox.showerror, "Тест політики", str(exc), parent=win)
            threading.Thread(target=work, daemon=True).start()

        def save():
            try:
                name = fields["name"].get().strip()
                if not name:
                    raise ValueError("Вкажіть назву каналу.")
                chat = normalize_chat_target(fields["chat"].get())
                p = current_policy(int(ch.id) if ch else 0)
                if p.target_max_chars < p.target_min_chars:
                    raise ValueError("Максимальна бажана довжина не може бути меншою за мінімальну.")
                cid = self.db.save_channel(
                    channel_id=ch.id if ch else None,
                    name=name,
                    telegram_chat_id=chat,
                    editorial_profile=p.purpose,
                    enabled=enabled.get(), include_source_link=False,
                    poll_interval_minutes=int(fields["poll"].get()),
                    min_publish_interval_minutes=int(fields["gap"].get()),
                    dedupe_window_hours=int(fields["dedupe"].get()),
                    max_age_hours=int(fields["age"].get()),
                    max_posts_per_cycle=int(fields["maxcycle"].get()),
                )
                p.channel_id = int(cid)
                self.db.rc59_save_channel_policy(p)
                sec = load_secrets()
                tok = fields["token"].get().strip()
                if tok:
                    sec.channel_bot_tokens[str(cid)] = tok
                else:
                    sec.channel_bot_tokens.pop(str(cid), None)
                save_secrets(sec)
                self.current_channel_id = cid
                win.destroy()
                self.refresh_all()
            except Exception as exc:
                messagebox.showerror("UA FREE Telegram Autopilot", str(exc), parent=win)

        bottom = ttk.Frame(win)
        bottom.pack(fill="x", padx=12, pady=(0, 10))
        ttk.Button(bottom, text="Зберегти", command=save).pack(side="right")
        ttk.Button(bottom, text="Показати фактичний prompt", command=show_prompt).pack(side="left", padx=4)
        ttk.Button(bottom, text="Тест редакційної політики", command=test_policy).pack(side="left", padx=4)
        if ch:
            def test_telegram():
                try:
                    tok = fields["token"].get().strip() or load_secrets().default_telegram_bot_token
                    name = test_bot(tok, fields["chat"].get())
                    messagebox.showinfo("UA FREE Telegram Autopilot", f"Telegram канал доступний: {name}", parent=win)
                except Exception as exc:
                    messagebox.showerror("UA FREE Telegram Autopilot", str(exc), parent=win)
            ttk.Button(bottom, text="Перевірити Telegram", command=test_telegram).pack(side="right", padx=8)

    MainWindow._channel_dialog = channel_dialog_rc59

    old_refresh_memory = getattr(MainWindow, "_rc48_refresh_memory", None)
    if old_refresh_memory:
        def refresh_memory_rc59(self):
            old_refresh_memory(self)
            var = getattr(self, "rc58_learning_summary", None)
            channel_id = int(getattr(self, "current_channel_id", 0) or 0)
            if var is not None:
                try:
                    var.set(generic_learning_summary(channel_id) if channel_id else "Оберіть канал.")
                except Exception as exc:
                    var.set(f"Редакторська пам'ять недоступна: {exc}")
        MainWindow._rc48_refresh_memory = refresh_memory_rc59


def install_rc59_universal_policy() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _install_database_patch()

    from . import production_pipeline as production
    from . import rc51_feedback as rc51
    from . import service as service_module

    rc51.score_against_feedback = score_against_feedback_rc59

    def decide(channel, article, recent, *, hard_limit=production.MEDIA_POST_HARD_LIMIT, format_marker=None):
        return decide_rc59(channel, article, recent, hard_limit=hard_limit, format_marker=format_marker)

    production.decide = decide
    service_module.decide = decide
    production.POST_FORMAT_PREFIX = "telegram-post-v36:"
    service_module.POST_FORMAT_PREFIX = "telegram-post-v36:"
    _install_ui()
    _INSTALLED = True
    LOG.info("RC59 installed: universal ChannelPolicy selector/writer; no channel-name routing; refusal guard active")
