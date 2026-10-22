"""Channel-scoped fail-closed civic relevance checks for opted-in monitoring feeds.

These checks use the *original source* and complement the model's classification.
They deliberately do not infer or publish battlefield coordinates.
"""
from __future__ import annotations

import re
from typing import Any

from .domain import ChannelMode

_CYR = re.I
_FORCE = re.compile(r"(?iu)\b(?:росіян\w*|російськ\w*|ворог\w*|окупант\w*|військ\w*|армі\w*|сил\w*\s+рф)\b")
_ADVANCE = re.compile(r"(?iu)\b(?:просува\w*|просун\w*|просуван\w*|наступ\w*|відступ\w*|відход\w*|захоп\w*|зайнял\w*\s+позиці\w*|контрол\w*\s+над)\b")
_PLACES = re.compile(r"(?iu)\b(?:напрям\w*|поблизу|біля|села|село|населен\w*\s+пункт\w*|позиці\w*|ділянц\w*|фронт\w*|област\w*|район\w*|карт\w*|територі\w*)\b")
_GENERIC_VACANCY = re.compile(r"(?iu)\b(?:актуальн\w*\s+вакансі\w*|підбірк\w*\s+вакансі\w*|вакансі\w*\s+(?:для|у|в)\s+впо|опублікувал\w*[^.!?\n]{0,100}\bвакансі\w*)")
_LOSS_ROUNDUP = re.compile(r"(?iu)\b(?:жмурк\w*|двохсот\w*|двухсот\w*|втрат\w*\s+серед\s+(?:російськ\w*\s+)?військов\w*|ліквідован\w*\s+окупант\w*)\b")
_CIVILIAN = re.compile(r"(?iu)\b(?:цивільн\w*|мирн\w*\s+жител\w*|пошкоджен\w*\s+будин\w*|житлов\w*\s+будин\w*|рятувальник\w*|постраждал\w*\s+мешканц\w*)\b")


# National daily loss counts from the General Staff are not a civic event in
# Zaporizhzhia merely because a local Telegram publisher forwarded them.
# Distinct from source-owned LOCAL civilian casualty or damage reports.
_DAILY_MILITARY_LOSS = re.compile(
    r"(?iu)(?:\b(?:втрат\w*|ліквідаці\w*|ліквідован\w*)\b.{0,90}"
    r"\b(?:за\s+добу|добов\w*|від\s+початку\s+війни)\b|"
    r"\b(?:добов\w*|за\s+добу)\b.{0,90}"
    r"\b(?:втрат\w*|ліквідаці\w*|ліквідован\w*)\b)"
)
_MILITARY_LOSS_TARGET = re.compile(
    r"(?iu)\b(?:росіян\w*|російськ\w*|росі\w*|армі\w*|"
    r"військ\w*|окупант\w*|ворог\w*|рф)\b"
)


_NATIONAL_NBU = re.compile(r"(?iu)\b(?:набу|національн\w*\s+банк\w*\s+україни|нбу)\b.{0,130}\b(?:обшук\w*|розслідуван\w*)|\b(?:обшук\w*|розслідуван\w*)\b.{0,130}\b(?:набу|національн\w*\s+банк\w*\s+україни|нбу)\b")
_EU_SANCTIONS = re.compile(r"(?iu)\b(?:єс|євросоюз\w*|європейськ\w*\s+союз\w*)\b.{0,180}\b(?:пакет\w*|санкці\w*)\b.{0,120}\b(?:росі\w*|рф)\b|\b(?:санкці\w*)\b.{0,130}\b(?:єс|євросоюз\w*)\b")
_LOCAL_ANCHOR = re.compile(r"(?iu)\b(?:запоріж\w*|запоріз\w*|мелітопол\w*|бердянськ\w*|енергодар\w*|токмак\w*|гуляйпол\w*|оріхів\w*|василів\w*|полог\w*|громад\w*\s+запорізьк\w*)\b")
_LOCAL_OUTCOME = re.compile(r"(?iu)\b(?:отрима\w*|відкри\w*|запровад\w*|нада\w*|запуска\w*|змін\w*|впровад\w*|використа\w*|передад\w*|підтрима\w*)\b")

# The operator's 21 Oct #71994 was an unrelated Putin/Trump/Witkoff clip
# copied by a Zaporizhzhia-branded feed. Channel name is not local evidence.
_GLOBAL_LEADER_CHAT = re.compile(
    r"(?iu)\b(?:трамп\w*|trump|віткофф\w*|уіткофф\w*|witkoff)\b"
)
_KREMLIN_INTERLOCUTOR = re.compile(
    r"(?iu)\b(?:путін\w*|путіном|putin|кремл\w*)\b"
)

def _value(row: Any, key: str) -> str:
    try:
        value = row[key]
    except (KeyError, TypeError, IndexError):
        value = getattr(row, key, "")
    return str(value or "")


_PROMO_JOIN_LINK = re.compile(r"(?iu)(?:https?://)?t\.me/\+[A-Za-z0-9_-]{8,}")
_PROMO_JOIN_PROMPT = re.compile(
    r"(?iu)\b(?:приєднал\w*|приєднуй\w*|заход\w*\s+в\s+(?:чат|груп\w*)|"
    r"видаля\w*|видалю\w*|лише\s+\d+\s+хвилин\w*)\b"
)
_URGENT_DELETE = re.compile(r"(?iu)\b(?:видаля\w*|видалю\w*)\b.{0,65}\b\d+\s*(?:хв|хвилин\w*)")
_MEANINGFUL_EVENT = re.compile(
    r"(?iu)\b(?:запоріж\w*|запоріз\w*|мелітопол\w*|бердянськ\w*|"
    r"енергодар\w*|оріхів\w*|громад\w*|містян\w*|мешканц\w*|"
    r"укритт\w*|евакуац\w*|допомог\w*|виплат\w*|"
    r"відбуд\w*|відкри\w*|запровад\w*|нада\w*|розклад\w*|"
    r"пошкодж\w*|постраждал\w*|пожеж\w*|будин\w*|школ\w*|"
    r"лікарн\w*|зустріч\w*|заход\w*|тренінг\w*|виставк\w*)\b"
)
_SPECULATIVE_SOCIAL = re.compile(r"(?iu)\b(?:як\s*би|уяв\w*|вигадан\w*|вваж\w*\s+тіктокер\w*)\b")
_SOCIAL_ENTERTAINMENT = re.compile(
    r"(?iu)\b(?:рілс\w*|reels?\b|тікток\w*|tiktok\w*|"
    r"блогер\w*|мем\w*|ш[іи]\s*відео)\b"
)
_PURE_SOCIAL_REACTION = re.compile(r"(?iu)\b(?:а\s+як\s+ви\s+відноситес\w*|що\s+думаєте\s+про\s+це)\b")


def _pure_invitation_noise(original: str) -> bool:
    """A vanishing join link is not a municipal event even in a local source."""
    if not _PROMO_JOIN_LINK.search(original):
        return False
    if not (_URGENT_DELETE.search(original) or _PROMO_JOIN_PROMPT.search(original)):
        return False
    # Do not suppress actual community service/instructions with a Telegram link.
    meaningful = re.sub(r"(?iu)https?://\S+", " ", original)
    meaningful = re.sub(r"(?iu)\b(?:приєднал\w*|приєднуй\w*|видаля\w*|видалю\w*)\b", " ", meaningful)
    return not bool(_MEANINGFUL_EVENT.search(meaningful))


def _unanchored_speculative_meme(original: str) -> bool:
    """Hypothetical reels without a source-owned local fact are not local news."""
    if not (_SPECULATIVE_SOCIAL.search(original) and _SOCIAL_ENTERTAINMENT.search(original)):
        return False
    # Actual regional exhibitions, screenings, people and civic initiatives survive.
    return not bool(_LOCAL_ANCHOR.search(original) or re.search(
        r"(?iu)\b(?:презентувал\w*|провел\w*|відкри\w*|"
        r"відбуд\w*|анонсува\w*|організувал\w*|"
        r"виставк\w*|показ\w*|фестивал\w*)\b",
        original,
    ))


def civic_relevance_exclusion(channel: Any, article: Any) -> str:
    """Fail closed only for a channel that has explicitly opted into the live gate."""
    if channel.mode != ChannelMode.MONITORING:
        return ""
    if "[LIVE_NOW_RC96]" not in str(channel.policy.rejection_rules or ""):
        return ""
    original = (_value(article, "title") + "\n" + _value(article, "raw_text"))[:8000]
    # A local publisher's label cannot make a nationwide military return
    # a municipal event. A verified Zaporizhzhia local outcome is exempt.
    from .repatriation_event_identity import national_repatriation_without_local_outcome
    if national_repatriation_without_local_outcome(article):
        return ("MONITORING_OFF_TOPIC_NATIONAL_REPATRIATION: "
                "загальноукраїнська репатріація без встановленого зв'язку з громадами області")
    # v2.2.14: High-confidence source-owned noise veto, independent of AI labels
    # and the name/geography of the newsroom that forwarded it.
    if _pure_invitation_noise(original):
        return "MONITORING_PROMO_JOIN_BAIT: тимчасове запрошення до чату без місцевої події або послуги"
    if _unanchored_speculative_meme(original):
        return "MONITORING_NONLOCAL_MEME: вигаданий інтернет-сюжет без факту чи події громади"
    if (_GLOBAL_LEADER_CHAT.search(original) and _KREMLIN_INTERLOCUTOR.search(original)
        and not _LOCAL_ANCHOR.search(original)):
        return "MONITORING_OFF_TOPIC_GLOBAL_CLIP: дипломатичний кліп без джерельного факту про громади регіону"
    # A source's geographic channel name does not turn national or EU policy
    # into a municipal announcement. Require an explicit local outcome for
    # high-confidence national-only categories; keep genuine local impacts.
    if (_NATIONAL_NBU.search(original) or _EU_SANCTIONS.search(original)) and not (
        _LOCAL_ANCHOR.search(original) and _LOCAL_OUTCOME.search(original)
    ):
        return "MONITORING_OFF_TOPIC: загальнонаціональний/міжнародний сюжет без конкретного результату для громади"
    if _FORCE.search(original) and _ADVANCE.search(original) and _PLACES.search(original):
        return "MONITORING_TACTICAL_UPDATE: поточні зміни бойових позицій/наступу не є цивільною завершеною подією"
    if _GENERIC_VACANCY.search(original):
        return "MONITORING_OFF_TOPIC: загальна добірка вакансій без конкретної місцевої події"
    if (_DAILY_MILITARY_LOSS.search(original)
        and _MILITARY_LOSS_TARGET.search(original)
        and not _LOCAL_ANCHOR.search(original)
        and not _CIVILIAN.search(original)):
        return "MONITORING_OFF_TOPIC_DAILY_LOSSES: загальнонаціональний підрахунок військових втрат без місцевої цивільної події"
    if _LOSS_ROUNDUP.search(original) and not _CIVILIAN.search(original):
        return "MONITORING_OFF_TOPIC: військові втрати/непідтверджена бойова хроніка без цивільного підсумку"
    return ""
