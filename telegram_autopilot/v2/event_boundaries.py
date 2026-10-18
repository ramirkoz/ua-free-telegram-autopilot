"""Conservative event boundary extraction for monitoring sources.

This is an event-integrity safety classifier, not a semantic story splitter.
It identifies independent announcement categories and evidence spans while
leaving ambiguous records unmodified and unavailable for automatic rewriting.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("lost_animal", re.compile(r"(?iu)(?:\b(?:загубився|зник|приблудився|знайшли|шукають)\b.{0,90}\b(?:собак\w*|пес\w*|хаскі|кіт|кот\w*|тварин\w*)\b|\b(?:хаскі|собак\w*|пес\w*|кіт|кот\w*)\b.{0,100}\b(?:приблудився|шукають|загубився|зник|знайшли)\b)")),
    ("lost_property", re.compile(r"(?iu)(?:\b(?:загуб\w*|втратив\w*|знайшли|шукають)\b.{0,100}\b(?:документ\w*|папк\w*|ключ\w*|гаман\w*)\b|\b(?:документ\w*|папк\w*|ключ\w*|гаман\w*)\b.{0,100}\b(?:загуб\w*|втратив\w*|знайшли|шукають)\b)")),
    ("road_incident", re.compile(r"(?iu)\b(?:дтп|дорожньо-транспортн\w* пригод\w*|аварі\w* на дорозі)\b")),
    ("air_alert", re.compile(r"(?iu)\b(?:повітряна тривога|загроза удару|ракетна небезпека)\b")),
    ("community_event", re.compile(r"(?iu)\b(?:арттерапевтичн\w* зустріч\w*|день громади|святков\w* захід\w*|урочист\w* частина)\b")),
)


@dataclass(frozen=True)
class EventSpan:
    category: str
    start: int
    end: int
    evidence: str


@dataclass(frozen=True)
class EventBoundaryDecision:
    categories: tuple[str, ...]
    spans: tuple[EventSpan, ...]
    ambiguous: bool

    @property
    def reason(self) -> str:
        return "MONITORING_MULTIPLE_UNRELATED_EVENTS" if self.ambiguous else ""


def classify_event_boundaries(source: str) -> EventBoundaryDecision:
    """Flag distinct independent announcements without fabricating split points.

    A post can legitimately discuss several concepts in one coherent story.
    Therefore only clearly unrelated announcement classes are separated here.
    """
    text = str(source or "")
    spans = []
    for category, pattern in _PATTERNS:
        for match in pattern.finditer(text):
            spans.append(EventSpan(category, match.start(), match.end(), match.group(0)))
    spans.sort(key=lambda item: (item.start, item.end))
    cats = tuple(dict.fromkeys(span.category for span in spans))
    # Independent classified notices have incompatible editorial intents;
    # a single story with generic overlapping terms isn't sufficient.
    unrelated = (
        {"lost_animal", "lost_property"},
        {"lost_animal", "road_incident"},
        {"lost_property", "road_incident"},
        {"community_event", "lost_property"},
        {"community_event", "lost_animal"},
    )
    mixed = any(group.issubset(set(cats)) for group in unrelated)
    return EventBoundaryDecision(cats, tuple(spans), mixed)
