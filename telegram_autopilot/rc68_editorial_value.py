from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Mapping

from .ai_router import Result

LOG = logging.getLogger("telegram_autopilot.rc68")
_INSTALLED = False
_PREV: dict[str, Any] = {}
_GATE_VERSION = 1


_VALUE_FIELDS = (
    "novelty",
    "consequence_or_insight",
    "mechanism",
    "reader_payoff",
    "retellability",
    "concrete_stakes",
    "why_now",
)


def _v(row: Mapping[str, Any] | Any, key: str, default: Any = "") -> Any:
    try:
        value = row[key]
    except Exception:
        value = getattr(row, key, default)
    return default if value is None else value


def _clean(value: Any, limit: int = 12000) -> str:
    return " ".join(str(value or "").split())[:limit]


def _active_db() -> Any | None:
    try:
        from . import rc51_feedback as rc51
        return rc51._ACTIVE_DB
    except Exception:
        return None


def _channel(channel_id: int) -> Any | None:
    db = _active_db()
    if db is None or not int(channel_id or 0):
        return None
    try:
        return db.get_channel(int(channel_id))
    except Exception:
        return None


def _monitoring(channel_or_id: Any) -> bool:
    if isinstance(channel_or_id, int):
        channel_or_id = _channel(channel_or_id)
    return str(getattr(channel_or_id, "channel_mode", "editorial") or "editorial").casefold() == "monitoring"


def _parse_json_object(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("RC68: AI не повернув JSON.")
    obj = json.loads(text[start : end + 1])
    if not isinstance(obj, dict):
        raise ValueError("RC68: AI JSON має бути об'єктом.")
    return obj


def _score(value: Any) -> int:
    try:
        return max(0, min(100, int(round(float(value or 0)))))
    except Exception:
        return 0


def _parse_value(raw: str) -> dict[str, Any]:
    obj = _parse_json_object(raw)
    data = {field: _score(obj.get(field)) for field in _VALUE_FIELDS}
    data["curiosity_only"] = bool(obj.get("curiosity_only", False))
    data["reason"] = _clean(obj.get("reason"), 600)
    data["one_sentence_payoff"] = _clean(obj.get("one_sentence_payoff"), 500)
    return data


def editorial_value_score(data: Mapping[str, Any]) -> int:
    weights = {
        "novelty": 0.14,
        "consequence_or_insight": 0.19,
        "mechanism": 0.14,
        "reader_payoff": 0.19,
        "retellability": 0.15,
        "concrete_stakes": 0.09,
        "why_now": 0.10,
    }
    return int(round(sum(_score(data.get(name)) * weight for name, weight in weights.items())))


def editorial_value_allowed(data: Mapping[str, Any]) -> tuple[bool, str, int]:
    score = editorial_value_score(data)
    novelty = _score(data.get("novelty"))
    consequence = _score(data.get("consequence_or_insight"))
    mechanism = _score(data.get("mechanism"))
    payoff = _score(data.get("reader_payoff"))
    retell = _score(data.get("retellability"))
    stakes = _score(data.get("concrete_stakes"))
    why_now = _score(data.get("why_now"))
    curiosity = bool(data.get("curiosity_only", False))

    if curiosity and consequence < 55 and payoff < 60:
        return False, "curiosity_only_without_payoff", score
    if score < 60:
        return False, f"editorial_value_score_{score}_below_60", score
    if payoff < 50:
        return False, f"reader_payoff_{payoff}_below_50", score
    if retell < 48:
        return False, f"retellability_{retell}_below_48", score
    if max(consequence, mechanism, stakes) < 52:
        return False, "no_consequence_mechanism_or_stakes", score
    if why_now < 32 and novelty < 78:
        return False, f"why_now_{why_now}_and_novelty_{novelty}_too_weak", score
    return True, "pass", score


def _channel_fit_prompt(policy: Any, article: Any, *, channel_id: int) -> str:
    from . import rc59_universal_policy as rc59
    from .evidence_pack import build_evidence_pack

    source = build_evidence_pack(article, char_budget=5600).text
    memory = rc59.topic_memory_block(channel_id)
    return f"""Ти CHANNEL-FIT SELECTOR Telegram-автопілота.

ТВОЯ ЄДИНА РОЛЬ: перевірити, чи SOURCE тематично і функціонально відповідає CHANNEL POLICY.
НЕ оцінюй, чи історія цікава широкій людині, чи має wow-ефект, чи її хочеться переказати. Це робить окремий системний gate після тебе.
НЕ вимагай сенсаційності. Не підмінюй політику каналу власними уявленнями про тематику.

{rc59.policy_text(policy)}

РЕДАКТОРСЬКА ПАМ'ЯТЬ ТЕМ:
{memory}

ДОДАТКОВА ІНСТРУКЦІЯ SELECTOR-А:
{_clean(getattr(policy, 'selector_extra_prompt', ''), 5000) or 'Немає.'}

SOURCE NAME:
{_clean(_v(article, 'source_name', ''), 300)}

SOURCE TITLE:
{_clean(_v(article, 'title', ''), 700)}

SOURCE EVIDENCE PACK:
{source}

Поверни ТІЛЬКИ JSON:
{{"decision":"publish" або "reject","fit_score":0..100,"reason":"коротко","angle":"якщо publish — кут, інакше порожньо","topic_tags":["2–5 тегів"]}}
""".strip()


def _run_channel_fit(policy: Any, article: Any, *, channel_id: int):
    from . import production_pipeline as production
    from . import rc59_universal_policy as rc59

    prompt = _channel_fit_prompt(policy, article, channel_id=channel_id)

    def validator(raw: str) -> None:
        rc59._parse_selector(raw)

    result = production.run_ai(
        prompt,
        validator=validator,
        max_output_tokens=340,
        local_prompt=prompt,
        local_max_output_tokens=360,
        cloud_timeout_seconds=22,
        local_timeout_seconds=18,
        task_timeout_seconds=60,
        local_repair=False,
        suppress_provider_on_quota=False,
        allowed_providers={"codex", "gemini", "groq", "nvidia", "cloudflare", "local"},
    )
    return result, rc59._parse_selector(result.text)


def _value_prompt(article: Any) -> str:
    from .evidence_pack import build_evidence_pack

    source = build_evidence_pack(article, char_budget=5800).text
    return f"""Ти UNIVERSAL EDITORIAL VALUE GATE Telegram-автопілота.

Ти НЕ знаєш назву, тематику, бренд або аудиторію каналу. Не намагайся їх вгадати.
Вважай, що матеріал УЖЕ пройшов окрему перевірку тематичної відповідності каналу.
Твоє завдання одне: визначити, чи SOURCE сам по собі вартий ОКРЕМОЇ редакційної публікації для живої людини.

Оціни 0..100:
- novelty: чи є реально нове/несподіване, а не просто незвичний об'єкт;
- consequence_or_insight: чи змінює це розуміння, рішення, можливості, ризики або дає сильний новий висновок;
- mechanism: чи є змістовне «як/чому це працює або сталося»;
- reader_payoff: що читач забере після прочитання, крім набору фактів;
- retellability: чи можна цікаво переказати суть одним реченням іншій людині;
- concrete_stakes: люди, гроші, технологія, масштаб, ризик, ресурс, поведінка або інший конкретний наслідок;
- why_now: чому це новина/матеріал саме зараз, а не довільний енциклопедичний факт.

curiosity_only=true, якщо основна привабливість тримається лише на екзотичності, великих числах, красивій картинці, знаменитості, гіпотетичному «уявіть, як виглядало б», рекорді без змістовного наслідку або іншому поверхневому wow без достатнього reader payoff.
Не карай сильну науку лише за відсутність практичної користі: нове відкриття, сильний механізм або справді нове розуміння можуть мати високий consequence_or_insight.
Не нагороджуй матеріал тільки за те, що тема сама по собі космос, AI, медицина, знаменитість, гроші або щось рідкісне.

SOURCE TITLE:
{_clean(_v(article, 'title', ''), 700)}

SOURCE EVIDENCE PACK:
{source}

Поверни ТІЛЬКИ JSON:
{{"novelty":0..100,"consequence_or_insight":0..100,"mechanism":0..100,"reader_payoff":0..100,"retellability":0..100,"concrete_stakes":0..100,"why_now":0..100,"curiosity_only":true або false,"one_sentence_payoff":"що саме читач забере одним реченням","reason":"коротке пояснення"}}
""".strip()


def _save_value(article: Any, data: Mapping[str, Any], allowed: bool, reason_code: str, score: int) -> None:
    db = _active_db()
    article_id = int(_v(article, "id", 0) or 0)
    if db is None or not article_id:
        return
    payload = dict(data)
    payload.update(version=_GATE_VERSION, allowed=bool(allowed), score=int(score), reason_code=str(reason_code))
    stamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    try:
        with db.connect() as con:
            con.execute(
                "UPDATE articles SET editorial_value_score=?,editorial_value_json=?,editorial_value_reason=?,editorial_value_checked_at=? WHERE id=?",
                (int(score), json.dumps(payload, ensure_ascii=False, separators=(",", ":")), _clean(data.get("reason"), 800), stamp, article_id),
            )
    except Exception as exc:
        LOG.warning("RC68 value diagnostics save failed article_id=%s: %s", article_id, exc)


def _cached_value(article: Any) -> dict[str, Any] | None:
    raw = str(_v(article, "editorial_value_json", "") or "").strip()
    if not raw:
        return None
    try:
        obj = json.loads(raw)
    except Exception:
        return None
    if not isinstance(obj, dict) or int(obj.get("version", 0) or 0) != _GATE_VERSION:
        return None
    return obj


def _run_value_gate(article: Any) -> tuple[dict[str, Any], bool, str, int, Any | None]:
    cached = _cached_value(article)
    if cached is not None:
        allowed, code, score = editorial_value_allowed(cached)
        return cached, allowed, code, score, None

    from . import production_pipeline as production

    prompt = _value_prompt(article)

    def validator(raw: str) -> None:
        _parse_value(raw)

    result = production.run_ai(
        prompt,
        validator=validator,
        max_output_tokens=360,
        local_prompt=prompt,
        local_max_output_tokens=380,
        cloud_timeout_seconds=22,
        local_timeout_seconds=18,
        task_timeout_seconds=60,
        local_repair=False,
        suppress_provider_on_quota=False,
        allowed_providers={"codex", "gemini", "groq", "nvidia", "cloudflare", "local"},
    )
    data = _parse_value(result.text)
    allowed, code, score = editorial_value_allowed(data)
    _save_value(article, data, allowed, code, score)
    return data, allowed, code, score, result


def _monitoring_exclusions(policy: Any) -> str:
    try:
        from . import rc59_universal_policy as rc59
        default = _clean(rc59.ChannelPolicy().rejection_rules, 12000).casefold()
    except Exception:
        default = ""
    current = _clean(getattr(policy, "rejection_rules", ""), 12000)
    if not current or current.casefold() == default:
        return ""
    return current


def _monitoring_selector(policy: Any, article: Any, *, channel_id: int):
    exclusions = _monitoring_exclusions(policy)
    if not exclusions:
        result = Result("monitoring-pass", "local-rule", "rc68-monitoring-bypass", "RC68 monitoring bypass")
        return result, {
            "decision": "publish",
            "fit_score": 100,
            "reason": "RC68 MONITORING_BYPASS: editorial-value та thematic-interest gates не застосовуються.",
            "angle": "Передай новий факт точно, стисло і без оцінки його цікавості.",
            "topic_tags": [],
        }

    from . import production_pipeline as production
    from .evidence_pack import build_evidence_pack

    source = build_evidence_pack(article, char_budget=5000).text
    prompt = f"""Ти MONITORING EXCLUSION GATE.
Канал працює в режимі моніторингу. НЕ оцінюй цікавість, важливість, wow-ефект, broad appeal, editorial value, силу гачка або тематичний баланс.
Матеріал за замовчуванням ПРОХОДИТЬ.
Відхили його ТІЛЬКИ якщо він ЧІТКО підпадає під одну з ЯВНИХ EXCLUSION RULES нижче. Якщо правило не збігається або є сумнів — publish.

EXCLUSION RULES:
{exclusions}

SOURCE NAME:
{_clean(_v(article, 'source_name', ''), 300)}
SOURCE TITLE:
{_clean(_v(article, 'title', ''), 700)}
SOURCE:
{source}

Поверни ТІЛЬКИ JSON:
{{"excluded":true або false,"reason":"яке конкретне exclusion rule спрацювало або 'none'"}}
""".strip()

    def parse(raw: str) -> tuple[bool, str]:
        obj = _parse_json_object(raw)
        return bool(obj.get("excluded", False)), _clean(obj.get("reason"), 500)

    def validator(raw: str) -> None:
        parse(raw)

    try:
        result = production.run_ai(
            prompt,
            validator=validator,
            max_output_tokens=180,
            local_prompt=prompt,
            local_max_output_tokens=200,
            cloud_timeout_seconds=12,
            local_timeout_seconds=10,
            task_timeout_seconds=30,
            local_repair=False,
            suppress_provider_on_quota=False,
            allowed_providers={"codex", "gemini", "groq", "nvidia", "cloudflare", "local"},
        )
        excluded, reason = parse(result.text)
    except Exception as exc:
        LOG.warning("RC68 monitoring exclusion gate unavailable channel_id=%s; fail-open: %s", channel_id, exc)
        result = Result("monitoring-exclusion-degraded", "local-rule", "rc68-monitoring-fail-open", "RC68 monitoring fail-open")
        excluded, reason = False, f"gate unavailable; fail-open: {exc}"

    return result, {
        "decision": "reject" if excluded else "publish",
        "fit_score": 0 if excluded else 100,
        "reason": ("RC68 MONITORING_EXCLUSION: " if excluded else "RC68 MONITORING_PASS: ") + (reason or "none"),
        "angle": "" if excluded else "Передай новий факт точно, стисло і без оцінки його цікавості.",
        "topic_tags": [],
    }


def _run_selector(policy: Any, article: Any, *, channel_id: int = 0):
    if _monitoring(int(channel_id or 0)):
        return _monitoring_selector(policy, article, channel_id=int(channel_id or 0))

    fit_result, fit = _run_channel_fit(policy, article, channel_id=int(channel_id or 0))
    data = dict(fit)
    if str(data.get("decision") or "") != "publish":
        LOG.info(
            "RC68 CHANNEL_FIT_REJECT channel_id=%s article_id=%s fit=%s reason=%s",
            channel_id, _v(article, "id", "?"), data.get("fit_score", 0), _clean(data.get("reason"), 500),
        )
        return fit_result, data

    value, allowed, code, score, value_result = _run_value_gate(article)
    data["editorial_value_score"] = score
    data["editorial_value_reason"] = _clean(value.get("reason"), 500)
    if not allowed:
        data["decision"] = "reject"
        data["angle"] = ""
        data["reason"] = (
            f"RC68 EDITORIAL_VALUE_REJECT score={score}; code={code}; "
            f"payoff={_score(value.get('reader_payoff'))}; retell={_score(value.get('retellability'))}; "
            f"consequence={_score(value.get('consequence_or_insight'))}; mechanism={_score(value.get('mechanism'))}; "
            f"why_now={_score(value.get('why_now'))}; curiosity_only={int(bool(value.get('curiosity_only')))}. "
            + _clean(value.get("reason"), 420)
        )
        LOG.info("RC68 EDITORIAL_VALUE_REJECT channel_id=%s article_id=%s %s", channel_id, _v(article, "id", "?"), data["reason"])
        return value_result or fit_result, data

    data["reason"] = (
        f"RC68 EDITORIAL_VALUE_PASS score={score}; payoff={_score(value.get('reader_payoff'))}; "
        f"retell={_score(value.get('retellability'))}; consequence={_score(value.get('consequence_or_insight'))}; "
        f"mechanism={_score(value.get('mechanism'))}; why_now={_score(value.get('why_now'))}. "
        + _clean(data.get("reason"), 300)
    )
    LOG.info("RC68 EDITORIAL_VALUE_PASS channel_id=%s article_id=%s score=%s", channel_id, _v(article, "id", "?"), score)
    return value_result or fit_result, data


def _feedback_score(article: Any, rows: list[Any]):
    channel_id = int(_v(article, "channel_id", 0) or 0)
    if _monitoring(channel_id):
        from .rc51_feedback import FeedbackScore
        return FeedbackScore(0.0, 0.0, 0.0, False, 0, 0.0, 0.0, 0)
    return _PREV["feedback_score"](article, rows)


def _editorial_hold_reason(channel: Any, tags: Any, recent: list[Any], *, now: datetime | None = None) -> str:
    if _monitoring(channel):
        return ""
    return _PREV["editorial_hold"](channel, tags, recent, now=now)


def _raw_monitoring_pending(db: Any, channel_id: int, limit: int = 20):
    from .rc66_clusters import composite_row

    with db.connect() as con:
        rows = con.execute(
            """SELECT a.*,s.name AS source_name,s.priority AS source_priority
               FROM articles a JOIN sources s ON s.id=a.source_id
               WHERE a.channel_id=? AND a.cluster_parent_id IS NULL AND (
                   a.status='new' OR (
                       a.status='retry' AND (
                           a.next_retry_at IS NULL OR a.next_retry_at='' OR datetime(a.next_retry_at)<=datetime('now')
                       )
                   )
               )
               ORDER BY CASE WHEN a.status='new' THEN 0 ELSE 1 END,
                        CASE WHEN a.status='new' THEN a.id END DESC,
                        CASE WHEN a.status='retry' THEN datetime(COALESCE(NULLIF(a.next_retry_at,''),a.discovered_at)) END ASC,
                        a.id DESC
               LIMIT ?""",
            (int(channel_id), max(1, int(limit))),
        ).fetchall()
    return [composite_row(db, row) for row in rows]


def _pending_by_mode(db: Any, channel_id: int, limit: int = 20):
    try:
        channel = db.get_channel(int(channel_id))
    except Exception:
        channel = None
    if _monitoring(channel):
        return _raw_monitoring_pending(db, int(channel_id), limit)
    return _PREV["pending"](db, int(channel_id), limit)


def _db_init(db: Any) -> None:
    _PREV["db_init"](db)
    with db.connect() as con:
        db._ensure_column(con, "articles", "editorial_value_score", "INTEGER")
        db._ensure_column(con, "articles", "editorial_value_json", "TEXT NOT NULL DEFAULT ''")
        db._ensure_column(con, "articles", "editorial_value_reason", "TEXT NOT NULL DEFAULT ''")
        db._ensure_column(con, "articles", "editorial_value_checked_at", "TEXT")
        con.execute("CREATE INDEX IF NOT EXISTS idx_articles_editorial_value ON articles(channel_id,editorial_value_score,id)")


def install_rc68_editorial_value() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from . import rc59_universal_policy as rc59
    from . import rc66_editorial_queue as rc66
    from . import rc67_nonblocking_runtime as rc67
    from .database import Database

    _PREV.update(
        selector=rc59._run_selector,
        feedback_score=rc59.score_against_feedback_rc59,
        editorial_hold=rc66.editorial_hold_reason,
        pending=rc67._PREV.get("pending"),
        db_init=Database._init,
    )

    Database._init = _db_init
    rc59._run_selector = _run_selector
    rc59.score_against_feedback_rc59 = _feedback_score
    rc66.editorial_hold_reason = _editorial_hold_reason
    rc67._PREV["pending"] = _pending_by_mode

    LOG.info(
        "RC68 installed: universal Editorial Value Gate for every editorial channel; monitoring bypasses interest, reaction suppression, topic balance and diversity ordering while keeping dedupe/merge/update and explicit exclusions"
    )
    _INSTALLED = True
