"""Source-owned 2.3.33 editorial fixes proven by new operator false positives."""
from __future__ import annotations

import re
from typing import Any


def _v(row: Any, key: str) -> str:
    try:
        return str(row[key] or "")
    except (KeyError, IndexError, TypeError):
        return str(getattr(row, key, "") or "")


_FUTURE_BURIAL = re.compile(
    r"(?:\b(?:відбудеться|відбудуться|запланован\w*|планується)\b"
    r".{0,125}\b(?:поховання|похорон|прощання)\b|"
    r"\b(?:поховають|проведуть\s+(?:в\s+останню\s+путь|поховання|прощання))\b"
    r".{0,105}\b(?:\d{1,2}\s+(?:січня|лютого|березня|квітня|травня|червня|липня|серпня|вересня|жовтня|листопада|грудня)|завтра|у\s+понеділок|у\s+вівторок)|"
    r"\b\d{1,2}\s+(?:січня|лютого|березня|квітня|травня|червня|липня|серпня|вересня|жовтня|листопада|грудня)\b"
    r".{0,140}\b(?:поховають|відбудеться\s+(?:поховання|прощання)|прощатимуться)\b)",
    re.I | re.S,
)
_FUNERAL = re.compile(r"\b(?:поховання|похорон|поховають|прощання|прощатимуться)\b", re.I)
_DATE = re.compile(r"\b\d{1,2}\s+(?:січня|лютого|березня|квітня|травня|червня|липня|серпня|вересня|жовтня|листопада|грудня)\b", re.I)
_PAST = re.compile(r"\b(?:відбулося|відбувся|поховали|попрощалися|вчора\s+провели)\b", re.I)


def future_funeral_notice_reason_2333(article: Any) -> str:
    """Exact future burial/farewell event, without suppressing death reporting."""
    title = _v(article, "title")[:750]
    raw = _v(article, "raw_text")[:1500]
    lead = (raw or title)[:700]
    if not (_FUNERAL.search(title) or _FUNERAL.search(lead)):
        return ""
    if _FUTURE_BURIAL.search(lead) or _FUTURE_BURIAL.search(title):
        return "MONITORING_FUTURE_FUNERAL_NOTICE_2333"
    # Short clear 'will bury ... Monday' constructions without a dated title
    if re.search(r"\b(?:поховають|прощатимуться)\b", title, re.I) and not _PAST.search(title):
        return "MONITORING_FUTURE_FUNERAL_NOTICE_2333"
    return ""


_SURVEY_SUBJECT = re.compile(r"\b(?:universal\s+basic\s+income|ubi|"
                             r"безумовн\w*\s+базов\w*\s+дох[іо]д)\b", re.I)
_SURVEY_OPINION = re.compile(r"\b(?:public\s+opinion|support\s+for|"
                             r"across\s+party\s+lines|political\s+(?:attitudes|support)|"
                             r"respondents?|survey|attitudes|підтримк\w*|опитуван\w*)\b", re.I)
_ART_OR_CAMPAIGN = re.compile(r"\b(?:visual\s+design|advertising\s+campaign|"
                              r"creative\s+campaign|poster\s+design|brand\s+identity|"
                              r"художн\w*\s+проєкт|дизайн\w*\s+кампані\w*)\b", re.I)


def creative_survey_reason_2333(article: Any) -> str:
    """Hard source boundary for the observed non-creative UBI opinion report."""
    title = _v(article, "title")[:650]
    raw = _v(article, "raw_text")[:2200]
    if _SURVEY_SUBJECT.search(title) and _SURVEY_OPINION.search(title + "\n" + raw) and not _ART_OR_CAMPAIGN.search(title):
        return "CREATIVE_PUBLIC_POLICY_OPINION_SURVEY_NOT_CREATIVE_2333"
    return ""
