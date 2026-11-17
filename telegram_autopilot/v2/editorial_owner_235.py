"""2.3.35: bounded topical calibration from 3291 operator color decisions.

These are preference guidelines and high-precision source-backed *negative*
controls, not a per-article whitelist, publishing permit, or a change to
security, source integrity, event dedupe, Telegram receipts or channel cadence.
"""
from __future__ import annotations

import re
from typing import Any

SCIENCE_GUIDANCE_235 = (
    "ПОВЕРНЕНИЙ ЗАВЕРШЕНИЙ ВІДБІР 16.11.2026 (CTRL+UA: 412 ТАК, 365 НІ; "
    "184 цікаві матеріали первинний селектор помилково відкинув): "
    "НЕ вимагай наукового відкриття від кожної технологічної новини. "
    "Достатньо перевіреного предметного факту: новий ШІ-продукт та його "
    "можливості, вплив цифрової платформи, цікава інженерна конструкція, "
    "екологічний матеріал, дослідження біології, космос, кібербезпека, "
    "технологічна історія. Не називай нові моделі, лабораторні результати, "
    "безпекові зміни чи цікаву технологічну функцію 'не відкриттям' як "
    "достатню причину відхилення. Водночас відхиляй добірки звичайних "
    "PC-утиліт, налаштування голосових функцій телевізора, трюки для "
    "економії батареї та побутові меню CarPlay без нового технологічного "
    "факту. Окреме нове дослідження про доступність, безпеку чи застосування "
    "програми НЕ те саме, що how-to. Підтверджені факти > ентузіазм AI."
)

CREATIVE_GUIDANCE_235 = (
    "ПОВЕРНЕНИЙ ЗАВЕРШЕНИЙ ВІДБІР 16.11.2026 (ПРОДАНО!: 253 ТАК, 168 НІ; "
    "145 цікавих історій відхилено селектором): це НЕ тільки реклама, "
    "дизайн і товар. Самостійна цікава людська історія, романтичні "
    "відносини, поведінкова психологія, дивні випадки з тваринами, "
    "попкультура, гумор, історія мистецтва, ігри та несподівані факти "
    "також належать каналу, якщо справді мають конкретний підтверджений "
    "інформаційний гачок. Зокрема людські історії про розставання оператор "
    "підтвердив як цікаві; не відхиляй їх за відсутність бренду або ROI. "
    "Відрізняй конкретні історії людей від беззмістовної вірусної добірки "
    "мемів або банального рейтингу магазинів. Звичайні порівняння курятини "
    "у супермаркетах, базові поради щодо покупок і випадкові 'топ подарунків' "
    "не є креативною історією. Не блокуй усі numbered collections, усі "
    "психологічні дослідження чи усі дизайн-об'єкти одним правилом."
)

REGIONAL_GUIDANCE_235 = (
    "ЗЕЛЕНИЙ ВІДБІР 16.11.2026 (ГРОМАДИ 1075 ТАК, 1018 НІ) охоплює "
    "підтверджені місцеві зміни комунальних послуг, електроенергії, "
    "транспорту, допомоги ВПО і ветеранам, результат заходів та "
    "наслідки обстрілів. Не відкидай факт лише тому, що він стислий або "
    "згаданий чужим каналом: перевір оригінальне джерело. Це НЕ дозвіл "
    "публікувати чужі репости без підтвердження, чутки, рекламу, прості "
    "запрошення, тактичні поточні маршрути ракет/БПЛА чи неперевірені "
    "повідомлення про атаку. Гуманітарні запрошення, ритуальні пости і "
    "вебінари лишаються під раніше прямо схваленою політикою NO ANNOUNCEMENTS, "
    "поки власник прямо не змінить її."
)

# Narrow conjunctions requiring an original headline + its corresponding
# substantive source. These were operator-RED published controls. A new
# discovery about diagnostics/accessibility remains eligible.
_SCIENCE_DIAGNOSTIC_LIST = re.compile(
    r"(?iu)^\s*\d{1,2}\s+.{0,38}\b(?:pc|computer|windows)\s+"
    r"(?:tools?|apps?|programs?|utilities)\b.{0,100}\b(?:diagnos|fix|troubleshoot|problems?|issues?)"
)
_SCIENCE_ROKU_TROUBLESHOOT = re.compile(
    r"(?iu)(?:\broku\b.{0,80}(?:reading\s+(?:everything|aloud)|reads?\s+(?:everything|aloud)|"
    r"turn\s+off\s+(?:the\s+)?voice|screen\s+reader)|"
    r"(?:screen\s+reader|voice\s+guidance).{0,90}\broku\b)"
)
_SCIENCE_PLAIN_BATTERY_TIPS = re.compile(
    r"(?iu)(?:\b(?:tips?|tricks?|ways?)\b.{0,60}\b(?:extend|improve|save|last\s+longer)\b.{0,35}\b(?:laptop|battery)\b|"
    r"\b(?:laptop|battery)\b.{0,48}\b(?:tips?|tricks?)\b)"
)
_SCIENCE_CARPLAY_SETTINGS = re.compile(
    r"(?iu)\b(?:carplay|apple\s+carplay)\b.{0,95}\b(?:speed\s+camera|speed\s+trap|"
    r"warnings?|alerts?)\b"
)
_SCIENCE_INSTRUCTION = re.compile(
    r"(?iu)(?:\bhow\s+to\b|\btry\s+this\b|\btips?\b|\btricks?\b|"
    r"\bturn\s+(?:on|off)\b|\bsettings?\b|\bget\s+more\b|\b5\s+.{0,45}\btools?\b)"
)
_SCIENCE_NOVEL = re.compile(
    r"(?iu)\b(?:new\s+(?:research|study|invention|discovery|robot|sensor|method|technology)|"
    r"scientists?\s+(?:discover|develop|demonstrate)|"
    r"researchers?\s+(?:demonstrate|develop|unveil)|"
    r"breakthrough|experiment(?:al)?\s+(?:findings?|results?))\b"
)
_CREATIVE_GENERIC_GIFT_LIST = re.compile(
    r"(?iu)\b(?:\d{1,2}\s+)?(?:best|top|thoughtful|perfect)\s+gifts?\s+for\b"
)
_CREATIVE_GENERIC_SHOPPING = re.compile(
    r"(?iu)\b(?:gift\s+guide|our\s+picks|shopping\s+list|buying\s+guide)\b"
)

# Owner-reviewed 13–16 Nov: 51 of 52 creative headlines starting with a
# two/three-digit count were RED, including 47/48 Bored Panda enumerations.
# This is a genre preference, NOT a ban on one publisher, all photography,
# all human interest or numbers describing real research/events.
_BULK_ROUNDUP_COUNT_235 = re.compile(r"(?iu)^\s*[1-9][0-9]{1,2}\s+")
_BULK_ROUNDUP_SIGNAL_235 = re.compile(
    r"(?iu)\b(?:memes?|pics?|photos?|posts?|tweets?|times|"
    r"images?|stories|opinions?|comments?|responses?|moments?|"
    r"takes|fails?|secrets?|confessions?|screenshots?|"
    r"people|parents|guests|influencers|women|men|"
    r"gifts?|finds?|tips?|things?|facts?|"
    r"signs?|notes?|projects?|comics?|ads?|"
    r"snacks?|foods?|picks?|restaurants?|solvers?|mothers.in.law|liars?|"
    r"ranked|before.and.afters?|photos?graphers?)\b"
)
# Deliberate *review-only* positive control, the one numbered owner-GREEN
# headline. The article is NOT auto-approved: the LLM and source/fact gates
# must still independently judge it. Avoid a general 'relationships pass' rule.
_OWNER_GREEN_RELATIONSHIP_EXCEPTION_235 = re.compile(
    r"(?iu)^\s*66\s+(?:women\s+share\s+the\s+final\s+straw|real\s+breakup\s+stories\s+shared\s+by\s+women)\b"
)


def _field(row: Any, key: str) -> str:
    try:
        return str(row[key] or "")
    except (KeyError, IndexError, TypeError):
        return str(getattr(row, key, "") or "")


def owner_source_veto_235(role: str, article: Any) -> str:
    """Explicit owner-red ordinary advice/consumer lists, no ID/brand whitelist."""
    if role not in {"science", "creative"}:
        return ""
    title = _field(article, "title")[:450]
    body = _field(article, "raw_text")[:5000]
    if not title or not body:
        return ""
    if role == "science":
        if _SCIENCE_NOVEL.search(title):
            return ""  # Newsworthy source still needs editorial and fact QA.
        if _SCIENCE_DIAGNOSTIC_LIST.search(title) and re.search(
            r"(?iu)\b(?:troubleshoot|diagnos|maintenance|problems?|support|utilities)\b", body
        ):
            return "SCIENCE_ORDINARY_PC_DIAGNOSTIC_ROUNDUP_235"
        if (_SCIENCE_ROKU_TROUBLESHOOT.search(title)
                and _SCIENCE_INSTRUCTION.search(title)) and re.search(
            r"(?iu)\b(?:screen\s+reader|voice|accessibility|settings?)\b", body
        ):
            return "SCIENCE_ROKU_VOICE_HOWTO_235"
        if _SCIENCE_INSTRUCTION.search(title) and _SCIENCE_PLAIN_BATTERY_TIPS.search(title):
            return "SCIENCE_ROUTINE_BATTERY_TIPS_235"
        if _SCIENCE_INSTRUCTION.search(title) and _SCIENCE_CARPLAY_SETTINGS.search(title):
            return "SCIENCE_CARPLAY_SETTINGS_NOT_NEWS_235"
    else:
        # Source-only genre veto: owner rejected 51/52 numbered creative
        # compilations, not merely ones missing concrete examples. This gate
        # runs in selection AND prepublish, preserving safety and dedupe.
        if (_BULK_ROUNDUP_COUNT_235.search(title)
                and _BULK_ROUNDUP_SIGNAL_235.search(title)
                and not _OWNER_GREEN_RELATIONSHIP_EXCEPTION_235.search(title)):
            return "CREATIVE_ENUMERATED_SOCIAL_ROUNDUP_OWNER_RED_235"
        if _CREATIVE_GENERIC_GIFT_LIST.search(title) and _CREATIVE_GENERIC_SHOPPING.search(body):
            return "CREATIVE_GENERIC_GIFT_SHOPPING_LIST_235"
    return ""
