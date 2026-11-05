"""2.3.15: deterministic source-owned P0 teaser and legal-action guards.

The live #91610 source was a disappearing Telegram invite, not a news event.
A location, exclamation, or "first footage" does not prove an event.
Only narrow, source-provable action changes are vetoed; never rewrite facts.
"""
from __future__ import annotations

import re
from typing import Any


def _field(article: Any, key: str) -> str:
    try:
        value = article[key]
    except (KeyError, IndexError, TypeError):
        value = getattr(article, key, "")
    return str(value or "")


_INVITE = re.compile(r"(?iu)(?:https?://)?(?:t\.me|telegram\.me)/(?:\+|joinchat/)[a-z0-9_-]{8,}")
_SCARCITY = re.compile(
    r"(?iu)(?:видаля\w*|видалю\w*|зникн\w*|прибир\w*)"
    r"[^.!?\n]{0,70}(?:\d+\s*(?:хв|хвилин\w*)|скоро|зараз)|"
    r"(?:терміново\s+переглян\w*|всі\s+переглянул\w*|"
    r"перейдіть\s+за\s+посиланням|приєднуй\w*|приєднал\w*)"
)
_FOOTAGE = re.compile(
    r"(?iu)(?:перш\w*\s+(?:жахлив\w*\s+)?(?:кадр\w*|відео|знімк\w*)|"
    r"(?:жахлив\w*|шокуюч\w*)\s+(?:кадр\w*|відео))"
)
# This is a safety *exception* to a promotional teaser veto, NOT a general
# truth classifier. A place name, clips appearing, an emoji, or an invite
# are deliberately not evidence of a substantive reported event.
_EVENT = re.compile(
    r"(?iu)\b(?:"
    r"скасован\w*|скасову\w*|затриман\w*\s+поїзд\w*|"
    r"електропоїзд\w*\s+скасову\w*|"
    r"опрацювал\w*|ухвалил\w*|підписал\w*|"
    r"відбул\w*|провел\w*|передал\w*|отримал\w*|"
    r"відкрили|запрацювал\w*|запровадил\w*|змінил\w*|"
    r"пошкоджен\w*|зруйнован\w*|постраждал\w*|загинул\w*|"
    r"поранен\w*|затримал\w*|викрил\w*|забезпечил\w*|"
    r"відключен\w*|знеструмлен\w*|відновил\w*|"
    r"надаватим\w*|виплатил\w*|виділил\w*|"
    r"підтвердил\w*\s+наслідк\w*"
    r")\b"
)
_URL = re.compile(r"(?iu)https?://\S+")
_LAW = re.compile(r"(?iu)\b(?:правоохоронц\w*|поліц\w*|прокуратур\w*|слідч\w*|обвинувальн\w*|підозрюван\w*)\b")
_ARREST = re.compile(
    r"(?iu)\b(?:затримал\w*|затриман\w*|заарештувал\w*|заарештован\w*|"
    r"взял\w*\s+під\s+варту|взят\w*\s+під\s+варту|арештован\w*)\b"
)
_FINAL_APPROVAL = re.compile(
    r"(?iu)\b(?:затвердил\w*|затверджен\w*|схвалил\w*)\s+"
    r"(?:нов\w*\s+|оновлен\w*\s+)?"
    r"(положенн\w*\s+про\s+[а-яіїєґa-z'’\s-]{5,100})"
)
_DOC_MENTION = re.compile(r"(?iu)\bположенн\w*\s+про\s+[а-яіїєґa-z'’\s-]{5,100}")
_EXPLICIT_DOC_APPROVAL = re.compile(
    r"(?iu)(?:\b(?:затвердил\w*|затверджен\w*|схвалил\w*)\b"
    r"[^.!?\n]{0,95}\bположенн\w*\s+про\b|"
    r"\bположенн\w*\s+про\b[^.!?\n]{0,95}"
    r"\b(?:затвердил\w*|затверджен\w*|схвалил\w*)\b)"
)


def monitoring_invite_bait_reason(article: Any) -> str:
    """Reject only source-owned disappearing-invite teaser without an event.

    Safe even when the title and body duplicate: source evidence comes from
    the immutable body, with title as a fallback for title-only collectors.
    """
    raw = _field(article, "raw_text").strip() or _field(article, "title").strip()
    if not raw or not _INVITE.search(raw):
        return ""
    if not _SCARCITY.search(raw):
        return ""
    # Remove the invite URL and the call-to-action before checking real news.
    body = _URL.sub(" ", raw)
    if _EVENT.search(body):
        return ""
    if _FOOTAGE.search(body):
        return "MONITORING_UNVERIFIED_FOOTAGE_INVITE_2315"
    if len(body) < 500:
        return "MONITORING_DISAPPEARING_INVITE_NO_EVENT_2315"
    return ""


def source_action_certainty_issues(article: Any, final_text: str) -> tuple[str, ...]:
    """Catch two high-confidence operator-observed action/result upgrades."""
    source = _field(article, "raw_text")
    final = str(final_text or "")
    if not source or not final:
        return ()
    issues: list[str] = []
    if _LAW.search(source) and _ARREST.search(final) and not _ARREST.search(source):
        issues.append("FACT_LAW_ENFORCEMENT_EXPOSURE_NOT_ARREST_2315")
    # Approval must be attached to the *named document*, not generalized
    # from "21 items considered" or "relevant decisions were adopted".
    if _FINAL_APPROVAL.search(final) and _DOC_MENTION.search(source):
        if not _EXPLICIT_DOC_APPROVAL.search(source):
            issues.append("FACT_COUNCIL_AGENDA_NOT_DOCUMENT_APPROVAL_2315")
    return tuple(dict.fromkeys(issues))
