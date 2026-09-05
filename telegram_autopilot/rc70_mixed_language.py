from __future__ import annotations

import logging
from typing import Any

from . import rc45_policy as rc45
from . import rc69_media_language as rc69

LOG = logging.getLogger("telegram_autopilot.rc70")
_INSTALLED = False
_PREV_ACCEPTS = None
_PREV_UPDATE_ARTICLE = None

DIRECTION_UKRU_TO_UK = "ukru_to_uk"
DIRECTION_LABEL = "Українська / російська → Українська"


def accepts_input_rc70(direction: str, text: str) -> bool:
    """Accept Ukrainian and Russian items in one UA-output channel.

    Language is evaluated per material, not inferred from the channel as a whole.
    The individual UA->UA and RU->UA modes remain available for channels that
    intentionally want to restrict their source language.
    """
    value = str(direction or rc45.DIRECTION_EN_TO_UK).strip().casefold()
    if value == DIRECTION_UKRU_TO_UK:
        from .language import looks_ukrainian

        return (
            looks_ukrainian(text)
            or rc69.looks_russian(text)
            or rc45.looks_ukrainian_or_russian(text)
        )
    assert _PREV_ACCEPTS is not None
    return bool(_PREV_ACCEPTS(direction, text))


def _update_article_rc70(db: Any, article_id: int, **fields: Any) -> None:
    # The legacy service gate names accepted source language as "en" before the
    # RC45/RC69 wrappers correct it. Mixed UA/RU input must never remain tagged
    # as English merely because the channel accepts both languages.
    if (
        rc45._CURRENT_DIRECTION.get() == DIRECTION_UKRU_TO_UK
        and fields.get("language") == "en"
    ):
        fields["language"] = "uk-ru"
    assert _PREV_UPDATE_ARTICLE is not None
    _PREV_UPDATE_ARTICLE(db, int(article_id), **fields)


def install_rc70_mixed_language() -> None:
    global _INSTALLED, _PREV_ACCEPTS, _PREV_UPDATE_ARTICLE
    if _INSTALLED:
        return

    from .database import Database

    # content_direction() validates against this mapping, so registering the
    # value here makes the existing RC45 channel context use the mixed mode
    # without a channel-name special case or a destructive schema migration.
    rc45.DIRECTION_LABELS[DIRECTION_UKRU_TO_UK] = DIRECTION_LABEL

    _PREV_ACCEPTS = rc69.accepts_input
    _PREV_UPDATE_ARTICLE = Database.update_article

    # RC69's installed input-gate closure resolves rc69.accepts_input at call
    # time. Replacing that function upgrades the live gate for every channel.
    rc69.accepts_input = accepts_input_rc70
    Database.update_article = _update_article_rc70

    LOG.info(
        "RC70 installed: one UA-output channel may mix Ukrainian and Russian sources; language is gated per material"
    )
    _INSTALLED = True
