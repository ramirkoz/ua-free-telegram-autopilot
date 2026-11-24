"""2.3.55: source-only newsroom story brief, not a rewrite or a new AI call.

The actual article remains the only factual source.  Literal source snippets
are ranked for reader relevance and passed as *evidence hints*, never asserted
as an independently verified summary or sent directly to Telegram.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Any


def _read(article: Any, key: str) -> str:
    try:
        value = article[key]
    except (KeyError, IndexError, TypeError):
        value = getattr(article, key, "")
    return str(value or "")


_NOISE = re.compile(
    r"(?iu)^(?:read more|click here|advertisement|related stories|підписуйтесь|"
    r"дякуємо всім|разом до перемоги|детальніше за посиланням|"
    r"your membership|explore (?:projects|your membership)|creative tools|"
    r"design inspiration|latest on cpus|gpu insights|premium member|"
    r"limited.time premium|copy link|facebook|whatsapp|credit:|\(credit:|"
    r"published |by[a-z]|\d+\+ black friday deals|our newsletter|"
    r"in a nutshell|new on our site|read the full article)\b")
_SPECIFIC = re.compile(r"(?iu)(?:\d|\b(?:first|without|instead|fastest|record|" 
                       r"дослідник\w*|виявил\w*|створил\w*|перетворил\w*|" 
                       r"запустил\w*|вперше|завдяки|пошкоджен\w*|" 
                       r"загинул\w*|поранен\w*|виплат\w*|одерж\w*|" 
                       r"встановил\w*|повернув\w*|вдалося)\b)")
_LINKS = re.compile(r"(?i)https?://\S+")
_TOKENS = re.compile(r"(?u)[^\W_]{4,}")
_STOPWORDS = frozenset({"about","with","from","that","this","have","will","are","the","into", "their", "when", "what", "latest", "most", "those", "more", "after", "amid", "news", "study", "reveals", "report", "reports", "video", "review", "without", "these", "which", "them", "they", "після", "через", "коли", "новини", "відомо", "який", "україни", "року", "місті", "всі", "також"})


def _keywords(value: str) -> set[str]:
    return {t for t in (x.casefold() for x in _TOKENS.findall(str(value or ""))) if t not in _STOPWORDS}


def _evidence_candidates(raw: str) -> list[str]:
    text = _LINKS.sub(" ", str(raw or "")).replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    # Source bullet paragraphs may be glued with no line breaks; split only
    # on real terminal punctuation or explicit newlines / bullet markers.
    parts = re.split(r"(?<=[.!?…])\s+|\n+|(?=[•▪●]\s+)", text)
    return [p.strip(" \t•▪●") for p in parts if 24 <= len(p.strip()) <= 560 and not _NOISE.search(p.strip())]


@dataclass(frozen=True, slots=True)
class StoryBrief2355:
    role: str
    hints: tuple[str, ...]
    reader_goal: str

    def prompt_block(self, *, final: bool = False) -> str:
        phase = "ПЕРЕВІР ЗАДУМ, А НЕ ПЕРЕКАЗ" if final else "ЖУРНАЛІСТСЬКИЙ ЗАДУМ ДО НАПИСАННЯ"
        facts = "\n".join("- Цитата SOURCE: " + s[:260] for s in self.hints)
        return (
            f"{phase} [2.3.55; {self.role}]:\n"
            f"ЗАВДАННЯ ДЛЯ НЕПРОФІЛЬНОГО ЧИТАЧА: {self.reader_goal}\n"
            "Не переписуй DRAFT або SOURCE речення за реченням. "
            "Знайди в SOURCE найсильніший перевірений результат, несподіваний "
            "контраст або людський наслідок; саме він має бути в першому "
            "реченні. Не вигадуй подив, причинність, точні слова автора чи цитати. "
            "Назви учасника природно в першому абзаці, але не починай механічно "
            "з довгої назви установи. Далі дай 2–3 доречні перевірені деталі, "
            "що пояснюють головне. Закінчи підтвердженим фактом, не мораллю.\n"
            "ДОСЛІВНІ УРИВКИ SOURCE ДЛЯ ВИБОРУ АКЦЕНТУ (НЕ готовий пост):\n"
            + (facts or "- Уривків недостатньо; працюй безпосередньо із SOURCE.")
            + "\nВажливо: уривки лише підказки, не повний склад SOURCE. "
              "При суперечності чи браку контексту використовуй повний SOURCE. "
              "Не випускай сирі англійські фрази з цієї картки в український пост."
        )


def build_story_brief_2355(article: Any, *, monitoring: bool, commercial: bool, science: bool) -> StoryBrief2355:
    role = "regional" if monitoring else "creative" if commercial else "science" if science else "general"
    goal = {
        "regional": "Що реально змінилося, де, коли, кому це корисно та які підтверджені умови?",
        "creative": "Що саме незвичайне у предметі, вчинку або ідеї, як вона виглядає і працює?",
        "science": "Який перевірений результат, чим він незвичайний та що саме ще невідомо?",
        "general": "Яка головна подія та її доведений людський або практичний наслідок?",
    }[role]
    raw = _read(article, "raw_text")[:8500]
    items = _evidence_candidates(raw)
    title_terms = _keywords(_read(article, "title"))
    scored: list[tuple[int,int,str]] = []
    for i, item in enumerate(items[:50]):
        compact = " ".join(item.split())
        if len(compact) < 26:
            continue
        # Do not let a site's navigation, image credit or unrelated sale
        # displace the article's actual factual lead. The verified title
        # itself is a *search hint*, not a second fact source.
        overlap = len(title_terms & _keywords(compact))
        score = (4 if i == 0 else max(0, 5 - i // 2)) + min(32, overlap * 7)
        if title_terms and overlap == 0 and i < 8:
            score -= 8
        score += 7 if _SPECIFIC.search(compact) else 0
        score += 3 if 48 <= len(compact) <= 260 else 0
        score -= 6 if len(compact) > 350 else 0
        if role == "regional" and re.search(r"(?iu)\b(?:сьогодні|завтра|вчора|станом|годин|місті|громад|людей|осіб|дітей)\b",compact):
            score += 4
        if role == "creative" and re.search(r"(?iu)(?:unusual|weighs|without|design|built|made|вперше|незвичн|створил)",compact):
            score += 4
        scored.append((score, i, compact))
    chosen = sorted(sorted(scored,key=lambda x:(-x[0],x[1]))[:3],key=lambda x:x[1])
    return StoryBrief2355(role,tuple(x[2][:260] for x in chosen),goal)


__all__ = ["StoryBrief2355", "build_story_brief_2355"]
