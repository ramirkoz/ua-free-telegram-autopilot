from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class StoryTags:
    major: str
    minor: str
    entities: tuple[str, ...]
    keywords: tuple[str, ...]
    specifics: tuple[str, ...]

    def strong(self) -> set[str]:
        out = {f"entity:{x.casefold()}" for x in self.entities}
        out.update(f"keyword:{x.casefold()}" for x in self.keywords)
        out.update(f"spec:{x.casefold()}" for x in self.specifics)
        if self.minor:
            out.add(f"minor:{self.minor.casefold()}")
        return out

    def as_json(self) -> str:
        return json.dumps(
            {"major": self.major, "minor": self.minor, "entities": self.entities, "keywords": self.keywords, "specifics": self.specifics},
            ensure_ascii=False, separators=(",", ":"),
        )


def v(row: Mapping[str, Any] | Any, key: str, default: Any = "") -> Any:
    try:
        value = row[key]
    except Exception:
        value = getattr(row, key, default)
    return default if value is None else value


def marketing_channel(channel: Any) -> bool:
    text = f"{getattr(channel, 'name', '')} {getattr(channel, 'editorial_profile', '')}".casefold()
    return any(x in text for x in ("продано", "marketing", "advertis", "реклам", "бренд", "campaign"))


_GENERAL_MAJOR = (
    ("Medicine & Health", ("patient", "disease", "therapy", "treatment", "clinical", "kidney", "cancer", "drug", "fda", "cholesterol", "obesity", "chemotherapy", "transplant", "medical")),
    ("AI & Software", ("artificial intelligence", " ai ", "model", "agent", "algorithm", "software", "openai", "anthropic", "hugging face", "machine learning")),
    ("Consumer Tech & Hardware", ("smartphone", "laptop", "chip", "processor", "display", "oled", "battery", "nvidia", "lenovo", "tcl", "hardware")),
    ("Space & Astronomy", ("spacecraft", "planet", "mercury", "mars", "moon", "nasa", "esa", "telescope", "orbit", "asteroid", "space")),
    ("Animals & Nature", ("bear", "raccoon", "bird", "mosquito", "wildlife", "animal", "species", "forest", "ocean", "climate", "nature")),
    ("Science & Engineering", ("study", "researcher", "material", "steel", "physics", "chemistry", "experiment", "engineering", "laboratory", "scientist")),
    ("Security & Policy", ("tariff", "police", "firefighter", "cyber", "security", "privacy", "government", "regulation", "law", "policy")),
    ("Business & Platforms", ("acquire", "acquisition", "company", "platform", "market", "business", "startup", "revenue", "investment")),
)
_GENERAL_MINOR = (
    ("Xenotransplantation", ("pig kidney", "porcine kidney", "kidney transplant", "xenotransplant", "swine kidney")),
    ("Gene editing", ("crispr", "gene edit", "genetically modified", "genetically edited", "dna editing")),
    ("Cancer treatment", ("chemotherapy", "tumor", "cancer treatment", "oncology")),
    ("Metabolism & obesity", ("obesity", "cholesterol", "triglyceride", "metabolic", "weight loss")),
    ("Neurology", ("nerve damage", "neuropathy", "brain", "neurological", "memory")),
    ("AI models & agents", ("ai model", "language model", "agent", "hugging face", "open model")),
    ("Robotics", ("robot", "robotics", "physical ai")),
    ("Display & mobile", ("smartphone", "oled", "display", "nxtpaper", "phone")),
    ("PC hardware", ("laptop", "processor", "chip", "cooling", "airjet")),
    ("Planetary science", ("mercury", "mars", "venus", "planet", "spacecraft")),
    ("Wild animal behavior", ("bear", "raccoon", "birdsong", "animal behavior", "wildlife")),
    ("Materials & energy", ("stainless steel", "electrolyzer", "hydrogen", "material", "battery")),
)
_MARKETING_MAJOR = (
    ("Campaigns & Creative", ("campaign", "creative", "spot", "film", "advert", "commercial", "agency", "cannes", "ooh", "billboard")),
    ("Brand Experience", ("activation", "pop-up", "experience", "event", "exchange", "pawnshop", "store", "street", "times square")),
    ("Creators & Influencers", ("creator", "influencer", "tiktok creator", "youtube creator")),
    ("Commerce & Pricing", ("pricing", "price", "subscription", "checkout", "retail", "e-commerce", "loyalty", "discount", "purchase")),
    ("Platforms & Advertising", ("tiktok", "instagram", "meta", "youtube shorts", "strava", "platform", "adtech", "social media")),
    ("PR & Weird Marketing", ("pr stunt", "publicity", "weird", "viral", "papamobile", "gold exchange", "stunt")),
    ("Marketing Strategy", ("strategy", "consumer behavior", "brand growth", "research", "marketing mechanic")),
)
_MARKETING_MINOR = (
    ("Experiential activation", ("activation", "pop-up", "exchange", "event", "experience", "street poster")),
    ("OOH & city media", ("ooh", "billboard", "times square", "screen", "outdoor")),
    ("Branded entertainment", ("microdrama", "series", "film", "shorts", "storytelling")),
    ("Gaming creative", ("game", "gaming", "humankind", "trailer")),
    ("Creator mechanics", ("creator", "influencer", "ugc")),
    ("Pricing & conversion", ("pricing", "checkout", "discount", "subscription", "conversion")),
    ("Viral stunt", ("stunt", "viral", "pawnshop", "crane", "papamobile")),
)
_STOP = {"the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "with", "from", "by", "at", "as", "is", "are", "was", "were", "this", "that", "new", "how", "why", "into", "after", "before", "over", "under", "more", "first", "world", "could", "will", "its"}
_GENERIC = {"The", "New", "First", "World", "September", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"}
_ENTITY_RE = re.compile(r"\b(?:[A-Z][A-Za-z'’.-]{1,}|[A-Z]{2,})(?:\s+(?:[A-Z][A-Za-z'’.-]{1,}|[A-Z]{2,})){0,3}\b")
_NUMBER_RE = re.compile(r"\b\d+(?:[.,]\d+)?(?:\s?(?:%|days?|hours?|years?|million|billion|mm|cm|kg|gb|tb|hz|mah))?\b", re.I)
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9'’-]{2,}")


def _pick(text: str, mapping, fallback: str) -> str:
    low = f" {text.casefold()} "
    best = (0, fallback)
    for label, needles in mapping:
        score = sum(2 if len(n.strip()) > 10 else 1 for n in needles if n in low)
        if score > best[0]:
            best = (score, label)
    return best[1]


def extract_story_tags(title: str, text: str = "", *, marketing: bool = False) -> StoryTags:
    title = " ".join(str(title or "").split())
    sample = f"{title}\n{' '.join(str(text or '').split())[:4000]}"
    major = _pick(sample, _MARKETING_MAJOR if marketing else _GENERAL_MAJOR, "Other")
    minor = _pick(sample, _MARKETING_MINOR if marketing else _GENERAL_MINOR, "")
    entities: list[str] = []
    for m in _ENTITY_RE.finditer(title + "\n" + sample[:1200]):
        x = " ".join(m.group(0).split()).strip(" .,:;()[]")
        if x and x not in _GENERIC and x.casefold() not in _STOP and x not in entities:
            entities.append(x)
            if len(entities) >= 10:
                break
    words = [w.casefold() for w in _WORD_RE.findall(title) if w.casefold() not in _STOP]
    keywords: list[str] = []
    for width in (3, 2, 1):
        for i in range(max(0, len(words) - width + 1)):
            phrase = " ".join(words[i:i + width])
            if len(phrase) >= 5 and phrase not in keywords:
                keywords.append(phrase)
                if len(keywords) >= 12:
                    break
        if len(keywords) >= 12:
            break
    specifics: list[str] = []
    for m in _NUMBER_RE.finditer(sample[:1800]):
        x = " ".join(m.group(0).split()).casefold()
        if x not in specifics:
            specifics.append(x)
            if len(specifics) >= 8:
                break
    return StoryTags(major, minor, tuple(entities), tuple(keywords), tuple(specifics))


def parse_tags(raw: Any) -> StoryTags:
    try:
        data = json.loads(str(raw or "{}"))
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    return StoryTags(
        str(data.get("major") or "Other"), str(data.get("minor") or ""),
        tuple(str(x) for x in data.get("entities") or [] if str(x).strip()),
        tuple(str(x) for x in data.get("keywords") or [] if str(x).strip()),
        tuple(str(x) for x in data.get("specifics") or [] if str(x).strip()),
    )


def strong_overlap(a: StoryTags, b: StoryTags) -> set[str]:
    return a.strong() & b.strong()


def row_tags(db: Any, row: Any, channel: Any, *, persist: bool = True) -> StoryTags:
    parsed = parse_tags(v(row, "tags_json", "{}"))
    if parsed.major != "Other" or parsed.minor or parsed.entities or parsed.keywords:
        return parsed
    tags = extract_story_tags(str(v(row, "title", "")), str(v(row, "raw_text", "") or v(row, "teaser_text", "") or v(row, "event_summary", "")), marketing=marketing_channel(channel))
    if persist and db is not None:
        try:
            with db.connect() as con:
                con.execute("UPDATE articles SET tags_json=?,topic_major=?,topic_minor=? WHERE id=?", (tags.as_json(), tags.major, tags.minor, int(v(row, "id", 0) or 0)))
        except Exception:
            pass
    return tags


def related(a: StoryTags, b: StoryTags) -> bool:
    if a.minor and b.minor and a.minor == b.minor:
        return True
    return len([x for x in strong_overlap(a, b) if not x.startswith("minor:")]) >= 2
