from __future__ import annotations

from collections import Counter
import re
from typing import Any, Iterable, Mapping

_INSTALLED = False


def _row_value(row: Mapping[str, Any] | Any, key: str, default: str = "") -> str:
    try:
        value = row[key]
    except Exception:
        return default
    return default if value is None else str(value)


def _story(row: Mapping[str, Any] | Any) -> str:
    return "\n".join(
        part
        for part in (
            _row_value(row, "title"),
            _row_value(row, "teaser_text"),
            _row_value(row, "event_summary"),
            _row_value(row, "full_article_uk"),
            _row_value(row, "raw_text")[:6000],
        )
        if part
    )


_TOPIC_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "cyber",
        (
            "cve-", "vulnerability", "zero-day", "zero day", "ransomware", "malware",
            "backdoor", "phishing", "cybersecurity", "security flaw", "actively exploited",
            "уразлив", "кібер", "бекдор", "шкідлив", "фішинг", "злам",
        ),
    ),
    (
        "ai_models_agents",
        (
            "artificial intelligence", " ai ", "openai", "chatgpt", "claude", "anthropic",
            "gemini", "deepmind", "deepseek", "qwen", "llm", "language model", "agentic",
            " ai agent", "ai agent", "foundation model", "multimodal", " ші ", "нейромереж",
            "мовна модель", "агент",
        ),
    ),
    (
        "tools_open_source",
        (
            "open source", "open-source", "github", "repository", "plugin", "framework",
            "library", "toolkit", "developer tool", "free tool", "free course", "course",
            "dataset", "api", "cli", "extension", "опенсорс", "відкритий код", "github",
            "плагін", "фреймворк", "бібліотек", "інструмент", "курс",
        ),
    ),
    (
        "robotics_mobility",
        (
            "robot", "robotics", "humanoid", "android", "drone", "autonomous vehicle",
            "self-driving", "electric bike", "e-bike", "electric car", "exoskeleton",
            "робот", "гуманоїд", "дрон", "автономн", "електровел", "електромоб",
        ),
    ),
    (
        "science_health",
        (
            "study", "research", "scientist", "physics", "biology", "chemistry", "medical",
            "medicine", "clinical trial", "phase 3", "vaccine", "cancer", "genome", "brain",
            "neuron", "climate", "energy", "fusion", "battery", "дослідж", "вчен", "фізик",
            "біолог", "медиц", "вакцин", "рак", "мозок", "нейрон", "клімат", "енерг",
        ),
    ),
    (
        "space",
        (
            "space", "nasa", "esa", "spacex", "rocket", "orbit", "moon", "mars", "galaxy",
            "astronom", "telescope", "asteroid", "cosmos", "космос", "ракета", "орбіт",
            "місяц", "марс", "галак", "астроном", "телескоп",
        ),
    ),
    (
        "hardware_compute",
        (
            "gpu", "cpu", "chip", "semiconductor", "processor", "server", "data center",
            "datacenter", "memory", "display", "sensor", "quantum computer", "чип", "процесор",
            "сервер", "дата-центр", "пам'ят", "сенсор", "квантов",
        ),
    ),
    (
        "consumer_tech",
        (
            "windows", "android", "ios", "macos", "chrome", "browser", "smartphone", "iphone",
            "pixel", "xbox", "playstation", "nintendo", "headset", "glasses", "wearable",
            "браузер", "смартфон", "окуляр", "консоль", "windows",
        ),
    ),
    (
        "business_platforms",
        (
            "acquisition", "acquires", "funding", "valuation", "ipo", "antitrust", "regulator",
            "lawsuit", "platform", "subscription", "price cut", "market share", "стартап",
            "інвест", "оцінк", "ipo", "антимонопол", "регулятор", "підписк", "ринок",
        ),
    ),
)

_TOPIC_LABELS = {
    "cyber": "кібербезпека",
    "ai_models_agents": "ШІ/моделі/агенти",
    "tools_open_source": "інструменти/open source",
    "robotics_mobility": "робототехніка/мобільність",
    "science_health": "наука/медицина/енергетика",
    "space": "космос/астрономія",
    "hardware_compute": "hardware/обчислення",
    "consumer_tech": "споживчі технології",
    "business_platforms": "технобізнес/платформи",
}

_TOPIC_CAPS = {
    "cyber": 2,
    "ai_models_agents": 4,
    "tools_open_source": 3,
    "robotics_mobility": 3,
    "science_health": 3,
    "space": 2,
    "hardware_compute": 3,
    "consumer_tech": 3,
    "business_platforms": 2,
}

# RC38 treated every CVE/"critical vulnerability" as a balance bypass. In live use
# this let security feeds occupy the stream even though the balance gate existed.
# RC41 only bypasses the mix for genuinely broad emergencies or exceptional events.
_BROAD_IMPACT_SIGNALS = (
    "mass outage", "nationwide outage", "global outage", "emergency", "millions of users",
    "millions of devices", "billion users", "widespread attacks", "used in widespread attacks",
    "actively exploited zero-day", "zero-day used in attacks", "phase 3", "world record",
    "first successful", "масовий збій", "глобальний збій", "мільйонів користувач",
    "мільйонів пристро", "масові атаки", "нульового дня", "третя фаза", "світовий рекорд",
)

_PRACTICAL_SIGNALS = (
    "open source", "open-source", "github", "repository", "toolkit", "plugin", "framework",
    "library", "free tool", "free course", "course", "dataset", "download", "cli", "extension",
    "опенсорс", "відкритий код", "репозитор", "інструмент", "плагін", "фреймворк",
    "бібліотек", "безкоштовн", "курс", "завантаж",
)

_SHOPPING_SIGNALS = (
    "buying guide", "our picks", "best accessories", "best accessory", "deal", "discount",
    "coupon", "shop now", "gift guide", "купити", "знижк", "промокод", "добірка товар",
)


def primary_topic_rc41(row: Mapping[str, Any] | Any) -> str:
    title = f" {_row_value(row, 'title').casefold()} "
    text = f" {_story(row).casefold()} "
    best_name = ""
    best_score = 0
    for name, terms in _TOPIC_GROUPS:
        score = 0
        for term in terms:
            if term in text:
                score += 3 if term.strip() and term.strip() in title else 1
        if score > best_score:
            best_name = name
            best_score = score
    return best_name


def _broad_impact(row: Mapping[str, Any] | Any, topic: str) -> bool:
    text = f" {_story(row).casefold()} "
    if not any(signal in text for signal in _BROAD_IMPACT_SIGNALS):
        return False
    # Security gets no special privilege merely for being a CVE. It must also carry
    # one of the broad-impact signals above.
    return True


def topic_balance_reject_reason_rc41(
    article: Mapping[str, Any] | Any,
    recent: Iterable[Mapping[str, Any] | Any],
) -> str:
    topic = primary_topic_rc41(article)
    if not topic:
        return ""
    if _broad_impact(article, topic):
        return ""

    categories = [primary_topic_rc41(row) for row in list(recent)[:12]]
    categories = [item for item in categories if item]
    if len(categories) < 6:
        return ""

    last10 = categories[:10]
    last4 = categories[:4]
    count10 = Counter(last10)[topic]
    count4 = Counter(last4)[topic]
    cap = _TOPIC_CAPS.get(topic, 3)

    # Prevent short runs of nearly identical editorial slots even before the full
    # 10-post cap is reached. AI gets a little more room because it is core to CTRL+UA.
    short_cap = 3 if topic == "ai_models_agents" else 2
    if topic == "cyber":
        short_cap = 1

    if count10 >= cap or count4 >= short_cap:
        label = _TOPIC_LABELS.get(topic, topic)
        return (
            f"TOPIC_BALANCE_RC41_SKIP: тема «{label}» уже займає {count10} із останніх "
            f"{len(last10)} публікацій і {count4} із останніх {len(last4)}; наступний слот "
            "віддаємо іншій сильній технологічній історії."
        )
    return ""


def newsworthiness_reject_reason_rc41(article: Mapping[str, Any] | Any) -> str:
    """Keep RC37's gate, but rescue genuinely useful non-shopping tech resources."""
    from . import rc37_policy as rc37_module

    original = getattr(rc37_module, "_rc41_original_newsworthiness", None)
    if original is None:
        original = rc37_module.newsworthiness_reject_reason
    reason = original(article)
    if not reason:
        return ""

    text = f" {_story(article).casefold()} "
    if any(signal in text for signal in _SHOPPING_SIGNALS):
        return reason
    practical_hits = sum(1 for signal in _PRACTICAL_SIGNALS if signal in text)
    if practical_hits >= 2 and (
        "NEWSWORTHINESS_SKIP: гайд" in reason
        or "NEWSWORTHINESS_SKIP: конференційний" in reason
        or "NEWSWORTHINESS_SKIP: пояснювальний" in reason
    ):
        return ""
    return reason


def install_rc41_policy() -> None:
    """RC41: diversify CTRL+UA's live feed without touching factual/style safety."""
    global _INSTALLED
    if _INSTALLED:
        return

    from . import production_pipeline as production_module
    from . import rc37_policy as rc37_module
    from . import rc38_policy as rc38_module
    from . import service as service_module

    # Keep a stable pointer so repeated test installs/reloads do not recurse.
    if not hasattr(rc37_module, "_rc41_original_newsworthiness"):
        rc37_module._rc41_original_newsworthiness = rc37_module.newsworthiness_reject_reason

    rc37_module.newsworthiness_reject_reason = newsworthiness_reject_reason_rc41
    rc38_module.primary_topic = primary_topic_rc41
    rc38_module.topic_balance_reject_reason = topic_balance_reject_reason_rc41

    marker = "telegram-post-v26:"
    production_module.POST_FORMAT_PREFIX = marker
    service_module.POST_FORMAT_PREFIX = marker
    _INSTALLED = True
