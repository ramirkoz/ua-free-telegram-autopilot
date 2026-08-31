from __future__ import annotations

import logging
import statistics
import tkinter as tk
from datetime import datetime, timezone
from typing import Any, Mapping
from urllib.parse import urlsplit
from tkinter import ttk

from .models import Decision

LOG = logging.getLogger("telegram_autopilot.rc58")
_INSTALLED = False
_PREVIOUS_SCORE = None
_PREVIOUS_MEDIA_VALIDATOR = None

WINDOW_DAYS = 7

_CTRL_LABELS = {
    "ai": "AI / моделі / агенти",
    "cyber": "кібербезпека",
    "space": "космос",
    "science": "наука / дослідження",
    "engineering": "інженерні штуки",
    "robotics": "роботи / автоматизація",
    "chips_compute": "чипи / обчислення",
    "energy_infra": "енергія / інфраструктура",
    "bigtech_policy": "Big Tech / цифрові правила",
    "consumer_howto": "побутові інструкції",
    "product_review": "огляди / buying advice",
    "lifestyle": "lifestyle / побут",
    "gaming_entertainment": "ігри / entertainment",
    "personal_opinion": "особисті колонки / opinion",
    "marketing_trade": "маркетингова індустрія",
    "platform_utility": "дрібні оновлення платформ",
}

_MARKETING_LABELS = {
    "brand_activation": "бренд-активації",
    "campaign_creative": "рекламні кампанії / creative",
    "creator_economy": "creator / influencer механіки",
    "gamification": "гейміфікація",
    "ugc_community": "UGC / community",
    "pr_stunt": "PR-stunts / партизанські ходи",
    "experiential_ooh": "experiential / OOH",
    "viral_social": "вірусні social-механіки",
    "behavioral_insight": "поведінкові інсайти",
    "platform_utility_update": "службові оновлення платформ",
    "corporate_people": "кадрові перестановки",
    "conference_event": "анонси конференцій",
    "metrics_report": "чиста статистика платформ",
    "adtech_tooling": "API / SDK / adtech tooling",
}

_CTRL_TERMS = {
    "ai": ("artificial intelligence", " ai ", "chatgpt", "claude", "gemini", "grok", "llm", "model hardware", "machine learning", "neural", "agentic", "ai agent"),
    "cyber": ("cyber", "security", "malware", "ransomware", "breach", "zero-day", "zero day", "vulnerability", "hack", "infostealer", "phishing", "privacy", "exploit"),
    "space": ("nasa", "spacex", "starship", "space", "orbit", "satellite", "telescope", "moon", "mars", "astronom", "galaxy", "asteroid", "lagrange"),
    "science": ("research", "study", "scientist", "researcher", "nature communications", "cell biomaterials", "cern", "physics", "biology", "medical", "nanoparticle", "quantum", "plasma", "neuron", "brain"),
    "engineering": ("engineer", "prototype", "3d-print", "3d print", "esp32", "sensor", "device", "mechanism", "motor", "wireless brake", "solder", "vise", "browser tool"),
    "robotics": ("robot", "robotic", "automation", "autonomous", "manipulator", "robot arm"),
    "chips_compute": ("chip", "semiconductor", "gpu", "cpu", "tpu", "npu", "processor", "data center", "datacenter", "server", "compute", "hbm", "tsmc", "nvidia", "amd", "intel"),
    "energy_infra": ("battery", "energy", "grid", "nuclear", "power plant", "infrastructure", "electric", "reactor", "fusion", "solar"),
    "bigtech_policy": ("meta", "google", "apple", "microsoft", "amazon", "regulator", "antitrust", "digital services act", "dsa", "tariff", "policy", "court", "maps"),
    "consumer_howto": ("how to", "tips", "what should", "how-to", "improve", "settings", "mode food", "food mode", "clear cache", "clearing cache", "android auto", "bluetooth adapter", "usb adapter", "take better photos"),
    "product_review": ("review", "buying guide", "best ", "should you buy", "amazon", "price", "costs $", "costs £", "2tb review", "comparison", "versus", " vs "),
    "lifestyle": ("tiny house", "home", "wearable", "group chat", "divorce", "mindset", "fitness tracker", "camper", "house"),
    "gaming_entertainment": ("game", "gaming", "steam", "apple arcade", "movie", "actor", "music", "album", "ep ", "gamescom", "playdate"),
    "personal_opinion": ("author describes", "i used", "my life", "my wife", "column", "essay", "opinion", "author writes", "reviewer says"),
    "marketing_trade": ("marketing", "advertis", "brand", "cmo", "campaign", "creator economy", "pinterest presents"),
    "platform_utility": ("login with facebook", "one-tap", "one tap", "sdk", "api credits", "developer account", "sign-on", "sign on", "platform update"),
}

_MARKETING_TERMS = {
    "brand_activation": ("activation", "watch party", "pop-up", "pop up", "in-store", "instore", "brand experience", "sampling", "live event", "community event"),
    "campaign_creative": ("campaign", "ad campaign", "creative campaign", "commercial", "spot", "brand film", "creative", "advertising campaign"),
    "creator_economy": ("creator", "influencer", "tiktok creator", "youtube creator", "creator partnership", "influencer partnership"),
    "gamification": ("gamif", "badge", "award", "gem", "points", "leaderboard", "achievement", "reward", "virtual item", "recognition award"),
    "ugc_community": ("ugc", "user-generated", "community", "fan-made", "fans created", "remix", "participation", "challenge"),
    "pr_stunt": ("stunt", "guerrilla", "ambush marketing", "surprise", "fake", "pr move", "publicity stunt", "spectacle"),
    "experiential_ooh": ("ooh", "out-of-home", "billboard", "experiential", "installation", "projection", "street activation", "mural"),
    "viral_social": ("viral", "meme", "trend", "social-first", "shareable", "repost", "remix", "challenge", "duet", "stitch", "went viral"),
    "behavioral_insight": ("behavior", "behaviour", "discovery", "discover news", "shifts to", "preference", "gen z", "gen alpha", "audience habit", "usage pattern"),
    "platform_utility_update": ("login with facebook", "one-tap", "one tap", "limited login", "sdk", "api credits", "developer account", "sign-on", "sign on", "new api", "platform update"),
    "corporate_people": ("appointed", "joins", "hired", "chief marketing", "cmo", "chief customer", "marketer moves", "new role", "promoted"),
    "conference_event": ("conference", "presents event", "virtual event", "september 17", "speakers", "sessions will", "annual presentation", "webinar"),
    "metrics_report": ("active users", "monthly active", "million users", "user growth", "year over year", "year-on-year", "dsa report", "reporting showed"),
    "adtech_tooling": ("api", "sdk", "developer", "adtech", "analytics tool", "login", "sign-on", "developer account"),
}

_CTRL_CORE = {"ai", "cyber", "space", "science", "engineering", "robotics", "chips_compute", "energy_infra", "bigtech_policy"}
_CTRL_UNWANTED = {"consumer_howto", "product_review", "lifestyle", "gaming_entertainment", "personal_opinion", "marketing_trade", "platform_utility"}
_MARKETING_MECHANICS = {"brand_activation", "campaign_creative", "creator_economy", "gamification", "ugc_community", "pr_stunt", "experiential_ooh", "viral_social", "behavioral_insight"}
_MARKETING_LOW_VALUE = {"platform_utility_update", "corporate_people", "conference_event", "metrics_report", "adtech_tooling"}
_AUDIO_EXTENSIONS = (".wav", ".mp3", ".m4a", ".aac", ".flac", ".opus", ".oga", ".ogg")


def _row_value(row: Mapping[str, Any] | Any, key: str, default: Any = "") -> Any:
    try:
        value = row[key]
    except Exception:
        value = getattr(row, key, default)
    return default if value is None else value


def channel_kind(channel: Any) -> str:
    text = f"{getattr(channel, 'name', '')} {getattr(channel, 'editorial_profile', '')}".casefold()
    if "продано" in text or "marketing" in text or "реклам" in text or "brand" in text:
        return "marketing"
    if "ctrl+ua" in text or "ctrl ua" in text:
        return "ctrlua"
    return "generic"


def _text(article: Any) -> str:
    return " ".join(str(part or "") for part in (
        _row_value(article, "title"), _row_value(article, "raw_text"),
        _row_value(article, "event_summary"), _row_value(article, "teaser_text"),
        _row_value(article, "source_name"),
    )).casefold()


def classify_facets(article: Any, kind: str) -> set[str]:
    text = f" {_text(article)} "
    terms = _MARKETING_TERMS if kind == "marketing" else _CTRL_TERMS
    return {facet for facet, needles in terms.items() if any(needle in text for needle in needles)}


def _labels(kind: str) -> dict[str, str]:
    return _MARKETING_LABELS if kind == "marketing" else _CTRL_LABELS


def editorial_reject_reason(channel: Any, article: Any) -> str:
    kind = channel_kind(channel)
    if kind == "generic":
        return ""
    facets = classify_facets(article, kind)
    if kind == "ctrlua":
        core = facets & _CTRL_CORE
        unwanted = facets & _CTRL_UNWANTED
        if unwanted and not core:
            pretty = ", ".join(_CTRL_LABELS[x] for x in sorted(unwanted))
            return f"RC58 CTRL selector: не формат научпоп/tech-дайджесту ({pretty})."
        if not core:
            return "RC58 CTRL selector: немає достатньої наукової, технологічної, космічної або кібербезпекової історії."
        if unwanted and len(core) == 1 and not (core & {"science", "engineering", "cyber", "space", "robotics"}):
            pretty = ", ".join(_CTRL_LABELS[x] for x in sorted(unwanted))
            return f"RC58 CTRL selector: побутова/оглядова рамка переважає над новиною ({pretty})."
        return ""
    mechanics = facets & _MARKETING_MECHANICS
    low = facets & _MARKETING_LOW_VALUE
    if not mechanics:
        if low:
            pretty = ", ".join(_MARKETING_LABELS[x] for x in sorted(low))
            return f"RC58 ПРОДАНО selector: немає цікавої маркетингової механіки; це {pretty}."
        return "RC58 ПРОДАНО selector: матеріал не містить кампанії, вірусної/creator/community механіки або поведінкового інсайту."
    if ("corporate_people" in facets or "conference_event" in facets) and len(mechanics) == 1 and "campaign_creative" in mechanics:
        return "RC58 ПРОДАНО selector: кадрова/івентова новина без конкретної механіки, яку варто переказати."
    return ""


def _parse_dt(value: Any) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _facet_similarity(candidate: set[str], previous: set[str]) -> float:
    if not candidate or not previous:
        return 0.0
    shared = len(candidate & previous)
    if shared <= 0:
        return 0.0
    containment = shared / max(1, min(len(candidate), len(previous)))
    jaccard = shared / max(1, len(candidate | previous))
    return min(1.0, 0.7 * containment + 0.3 * jaccard)


def semantic_editor_adjustment(article: Any, feedback_rows: list[Any], kind: str) -> tuple[float, float, float]:
    candidate = classify_facets(article, kind)
    if not candidate:
        return 0.0, 0.0, 0.0
    now = datetime.now(timezone.utc)
    positive = negative = 0.0
    for row in feedback_rows:
        likes = max(0, int(_row_value(row, "likes", 0) or 0))
        dislikes = max(0, int(_row_value(row, "dislikes", 0) or 0))
        signal = likes - 2.0 * dislikes  # 🔥 is style only.
        if signal == 0:
            continue
        sim = _facet_similarity(candidate, classify_facets(row, kind))
        if sim <= 0:
            continue
        published = _parse_dt(_row_value(row, "published_at") or _row_value(row, "checked_at"))
        age_hours = 24.0 * WINDOW_DAYS if published is None else max(0.0, (now - published).total_seconds() / 3600.0)
        if age_hours > 24.0 * WINDOW_DAYS:
            continue
        decay = 0.5 ** (age_hours / 96.0)
        value = sim * decay * signal * 1.35
        if value >= 0:
            positive += value
        else:
            negative += -value
    return positive - negative, positive, negative


def score_against_feedback_rc58(article: Any, feedback_rows: list[Any]):
    from . import rc51_feedback as rc51
    previous_fn = _PREVIOUS_SCORE or rc51.score_against_feedback
    previous = previous_fn(article, feedback_rows)
    kind = str(_row_value(article, "_rc58_kind", "") or "")
    if kind not in {"ctrlua", "marketing"}:
        kind = "marketing" if classify_facets(article, "marketing") else "ctrlua"
    sem, sem_pos, sem_neg = semantic_editor_adjustment(article, feedback_rows, kind)
    lexical_scale = 0.35
    return rc51.FeedbackScore(
        score=float(previous.score) * lexical_scale + sem,
        positive=float(previous.positive) * lexical_scale + sem_pos,
        negative=float(previous.negative) * lexical_scale + sem_neg,
        hard_suppress=bool(previous.hard_suppress),
        matched_article_id=int(previous.matched_article_id),
        matched_similarity=float(previous.matched_similarity),
        matched_age_hours=float(previous.matched_age_hours),
        rated_posts=int(previous.rated_posts),
    )


def _channel_contract(kind: str) -> str:
    if kind == "marketing":
        return """КОНТРАКТ КАНАЛУ ПРОДАНО!:
Це дайджест вірусного маркетингу, реклами, creator economy і способів привертати увагу, а НЕ стрічка всіх новин маркетингової індустрії.
У центрі поста завжди МЕХАНІКА: що саме бренд/платформа/автор зробили такого, що люди помітили, обговорювали, поширювали або захотіли повторити.
Починай із самої фішки, а не з CMO, SDK, API, DSA, звіту чи назви конференції.
Перевага: бренд-активації, social-first кампанії, creator collaborations, UGC/community, гейміфікація, меми, PR-stunts, нестандартний OOH/experiential, вірусні формати.
Якщо в SOURCE немає цікавої механіки, її НЕ вигадуй і не маскуй корпоративну новину красивим текстом.
Стиль: живо, просто, 2–3 короткі абзаци, без B2B-канцеляриту і без пояснень очевидного маркетологам."""
    return """КОНТРАКТ КАНАЛУ CTRL+UA:
Це короткий український научпоп/tech-дайджест для розумної людини БЕЗ обов'язкової технічної чи наукової освіти.
За 20–30 секунд читач має зрозуміти: що сталося, чому це цікаво, і одну деталь, яку хочеться переказати іншій людині.
Перше речення пояснює суть людською мовою. Одна думка на речення. Зазвичай 2–3 короткі абзаци, приблизно 350–650 символів.
Якщо без терміна можна обійтися — прибери його. Якщо термін потрібен — поясни при першій згадці простими словами.
Не перетворюй пост на наукову статтю, пресреліз, список характеристик, buying guide, огляд товару або інструкцію «як налаштувати».
Залиш максимум 2–3 числа, якщо саме вони допомагають зрозуміти історію. Пиши природною сучасною українською без кальок і псевдоекспертної мови.
Перед відповіддю мовчки перевір: «Чи зрозуміє це розумний 16-річний читач без Google?» Якщо ні — перепиши простіше."""


def build_ru_editor_prompt_rc58(channel: Any, article: Any, *, hard_limit: int) -> str:
    from .evidence_pack import build_evidence_pack
    kind = channel_kind(channel)
    source = build_evidence_pack(article, char_budget=5200).text
    facets = classify_facets(article, kind)
    labels = _labels(kind)
    facet_text = ", ".join(labels.get(x, x) for x in sorted(facets)) or "не визначено"
    return f"""Ты внутренний выпускающий редактор. Найди одну человечески понятную историю в SOURCE и подготовь КОРОТКИЙ план для украинского автора.

{_channel_contract(kind)}

Автоматические смысловые метки кандидата: {facet_text}.
Они помогают выбрать угол, но НЕ являются источником фактов.

Выбери 2–4 проверенных факта и одну деталь, за которую цепляется внимание. Выбрось справочную шелуху, корпоративные формулировки и лишние характеристики.
Не добавляй выводов, мотивов, прогнозов или новых фактов. SOURCE — единственный источник фактов.

SOURCE TITLE:
{str(_row_value(article, 'title') or '')[:360]}

SOURCE EVIDENCE PACK:
{source}

Верни только естественный редакторский план на русском, 220–600 знаков.""".strip()


def build_ua_writer_prompt_rc58(channel: Any, article: Any, russian_draft: str, *, hard_limit: int) -> str:
    from .evidence_pack import build_evidence_pack
    from .rc52_feedback import style_memory_block
    kind = channel_kind(channel)
    source = build_evidence_pack(article, char_budget=5800).text
    profile = " ".join(str(getattr(channel, "editorial_profile", "") or "").split())[:1800]
    style_memory = style_memory_block(channel, article, purpose="writing")
    return f"""Ти пишеш ФІНАЛЬНИЙ пост Telegram з нуля природною сучасною українською.

{_channel_contract(kind)}

ПРОФІЛЬ КОНКРЕТНОГО КАНАЛУ (тематичні уточнення; якщо тон/складність суперечать контракту вище, КОНТРАКТ МАЄ ПРІОРИТЕТ):
{profile or 'Не задано; дотримуйся контракту каналу вище.'}

ФАКТИЧНА БЕЗПЕКА:
- SOURCE EVIDENCE PACK — єдине джерело фактів;
- внутрішній план лише допомагає побачити історію, але не є доказом;
- не додавай нового числа, дати, сутності, причини, мотиву, оцінки або прогнозу;
- зберігай атрибуцію та невизначеність;
- без заголовка, URL, слова «Джерело», хештегів та емодзі;
- заверши повним реченням;
- жорсткий ліміт {int(hard_limit)} символів, але не намагайся його заповнити.

{style_memory}

SOURCE TITLE:
{str(_row_value(article, 'title') or '')[:360]}

SOURCE EVIDENCE PACK:
{source}

ВНУТРІШНІЙ ПЛАН (НЕ ДЖЕРЕЛО ФАКТІВ):
{str(russian_draft or '')[:1400]}

Поверни ТІЛЬКИ готовий Telegram-пост.""".strip()


def _audience_perf(row: Any, baseline: float) -> float:
    from .rc57_feedback_model import audience_performance_score
    return audience_performance_score(row, baseline)


def learned_summary(rows: list[Any], kind: str) -> str:
    labels = _labels(kind)
    now = datetime.now(timezone.utc)
    topic_scores: dict[str, float] = {}
    fire_count = 0
    latest = None
    audience_rates = []
    for row in rows:
        published = _parse_dt(_row_value(row, "published_at") or _row_value(row, "checked_at"))
        if published is not None and (latest is None or published > latest):
            latest = published
        if int(_row_value(row, "views", 0) or 0) >= 25:
            from .rc57_feedback_model import audience_raw_rate
            audience_rates.append(audience_raw_rate(row))
    baseline = statistics.median(audience_rates) if audience_rates else 0.0
    audience_scores: dict[str, float] = {}
    for row in rows:
        facets = classify_facets(row, kind)
        if not facets:
            continue
        likes = max(0, int(_row_value(row, "likes", 0) or 0))
        dislikes = max(0, int(_row_value(row, "dislikes", 0) or 0))
        fires = max(0, int(_row_value(row, "fires", 0) or 0))
        fire_count += fires
        published = _parse_dt(_row_value(row, "published_at") or _row_value(row, "checked_at"))
        age_hours = WINDOW_DAYS * 24 if published is None else max(0.0, (now - published).total_seconds() / 3600.0)
        decay = 0.5 ** (age_hours / 96.0)
        topic = (likes - 2.0 * dislikes) * decay
        audience = _audience_perf(row, baseline) * decay
        for facet in facets:
            topic_scores[facet] = topic_scores.get(facet, 0.0) + topic
            audience_scores[facet] = audience_scores.get(facet, 0.0) + audience
    positive = sorted(((v, k) for k, v in topic_scores.items() if v > 0.15), reverse=True)[:4]
    negative = sorted(((-v, k) for k, v in topic_scores.items() if v < -0.15), reverse=True)[:4]
    audience = sorted(((v, k) for k, v in audience_scores.items() if v > 0.20), reverse=True)[:3]
    chunks = []
    if positive:
        chunks.append("↑ Адміни хочуть більше: " + "; ".join(f"{labels.get(k,k)} {v:+.1f}" for v, k in positive))
    if negative:
        chunks.append("↓ Адміни хочуть менше: " + "; ".join(f"{labels.get(k,k)} {-v:+.1f}" for v, k in negative))
    if audience:
        chunks.append("↗ Аудиторія краще реагує: " + "; ".join(labels.get(k, k) for _v, k in audience))
    chunks.append(f"🔥 стильових голосів: {fire_count}")
    if latest is not None:
        chunks.append("Останні feedback-дані: " + latest.astimezone().strftime("%d.%m %H:%M"))
    return "\n".join(chunks) if chunks else "Ще замало реакцій, щоб показати редакційні закономірності."


def _install_ui_learning_summary() -> None:
    from .ui import MainWindow
    old_build = MainWindow._build
    old_refresh = MainWindow._rc48_refresh_memory

    def build_rc58(self):
        old_build(self)
        tab = getattr(self, "memory_tab", None)
        if tab is None:
            return
        box = ttk.LabelFrame(tab, text="Що система зрозуміла з реакцій", padding=8)
        box.pack(fill="x", pady=(8, 0))
        self.rc58_learning_summary = tk.StringVar(value="Ще замало реакцій для семантичного профілю.")
        ttk.Label(box, textvariable=self.rc58_learning_summary, wraplength=1140, justify="left").pack(anchor="w")

    def refresh_rc58(self):
        old_refresh(self)
        var = getattr(self, "rc58_learning_summary", None)
        if var is None:
            return
        channel_id = int(getattr(self, "current_channel_id", 0) or 0)
        if not channel_id:
            var.set("Оберіть канал.")
            return
        try:
            channel = self.db.get_channel(channel_id)
            rows = self.db.rc51_feedback_rows(channel_id, days=WINDOW_DAYS, limit=180)
            var.set(learned_summary(rows, channel_kind(channel)))
        except Exception as exc:
            var.set(f"Семантичний профіль недоступний: {exc}")

    MainWindow._build = build_rc58
    MainWindow._rc48_refresh_memory = refresh_rc58


def _install_media_filter() -> None:
    global _PREVIOUS_MEDIA_VALIDATOR
    from . import media, media_pipeline
    if _PREVIOUS_MEDIA_VALIDATOR is None:
        _PREVIOUS_MEDIA_VALIDATOR = media.valid_public_media
    previous = _PREVIOUS_MEDIA_VALIDATOR

    def valid_public_media_rc58(value: str):
        parsed = previous(value)
        if not parsed:
            return None
        kind, url = parsed
        path = urlsplit(url).path.casefold()
        if kind in {"video", "iframe"} and path.endswith(_AUDIO_EXTENSIONS):
            return None
        return kind, url

    media.valid_public_media = valid_public_media_rc58
    media_pipeline.valid_public_media = valid_public_media_rc58


def install_rc58_editorial_rebuild() -> None:
    global _INSTALLED, _PREVIOUS_SCORE
    if _INSTALLED:
        return
    from . import production_pipeline as production
    from . import rc40_policy as rc40
    from . import rc51_feedback as rc51
    from . import service as service_module

    _PREVIOUS_SCORE = rc51.score_against_feedback
    rc51.score_against_feedback = score_against_feedback_rc58
    rc40.build_russian_editorial_prompt = build_ru_editor_prompt_rc58
    rc40.build_ukrainian_bridge_prompt = build_ua_writer_prompt_rc58
    old_decide = production.decide

    def decide_rc58(channel, article, recent, *, hard_limit=production.MEDIA_POST_HARD_LIMIT, format_marker=None):
        reason = editorial_reject_reason(channel, article)
        if reason:
            LOG.info("RC58 selector REJECT article_id=%s channel=%s reason=%s", _row_value(article, "id", "?"), getattr(channel, "name", ""), reason)
            return Decision(
                decision="reject", duplicate_of=None, reason=reason,
                event_key="rc58-editorial-selector", event_summary=str(_row_value(article, "title") or "")[:1000],
                headline_uk="", telegram_teaser="", full_article_uk="", media_captions_uk={},
                confidence=0.99, provider="local-rule", model="rc58-channel-selector",
            )
        result = old_decide(channel, article, recent, hard_limit=hard_limit, format_marker=format_marker)
        if result.decision == "publish":
            result.reason = (str(result.reason or "") + " RC58 channel-specific selector/writer PASS.").strip()
        return result

    production.decide = decide_rc58
    service_module.decide = decide_rc58
    production.POST_FORMAT_PREFIX = "telegram-post-v35:"
    service_module.POST_FORMAT_PREFIX = "telegram-post-v35:"
    _install_media_filter()
    _install_ui_learning_summary()
    _INSTALLED = True
    LOG.info("RC58 installed: channel-specific selectors/writers, semantic reaction learning, visible learned profile, audio-not-video media guard")
