"""2.2.50: deterministic, source-bounded editorial blueprint for every news story.

The blueprint guides presentation, NOT factual conclusions. It does not add an
AI provider call, source, persistent database state, or publication veto.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


def _read(article: Any, key: str) -> str:
    try:
        value = article[key]
    except (KeyError, TypeError, IndexError):
        value = getattr(article, key, "")
    return str(value or "")


_SERVICE = re.compile(
    r"(?iu)\b(?:допомог\w*|підтримк\w*|консультац\w*|гаряч\w*\s+ліні\w*|"
    r"доступн\w*\s+(?:послуг\w*|консультац\w*)|psychological\s+support|"
    r"mental\s+health\s+service|free\s+consultation)\b"
)
_CONTACT = re.compile(r"(?i)(?:\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b|(?<!\d)\+?\d[\d\s()\-]{7,}\d(?!\d)|https?://)")
_CIVIC_CHANGE = re.compile(r"(?iu)\b(?:рішенн\w*|розпорядженн\w*|графік\w*|"
                            r"зареєстру\w*|реєстрац\w*|термін\w*|набір\w*|"
                            r"прийом\w*|змін\w*\s+розклад\w*)\b")
_CREATIVE = re.compile(r"(?i)\b(?:campaign|advertis\w*|creative|animation|brand|commercial)\b|"
                       r"(?iu)\b(?:кампані\w*|бренд\w*|реклам\w*|анімаці\w*)\b")
_HAND_CRAFT = re.compile(r"(?i)\b(?:hand[- ]drawn|traditional\s+animation|"
                         r"handmade|hand[- ]craft\w*|hand[- ]paint\w*)\b|"
                         r"(?iu)\b(?:ручн\w*\s+(?:анімаці\w*|робот\w*|малюванн\w*)|"
                         r"мальован\w*\s+вручну)\b")
_AI_MENTION = re.compile(r"(?i)\b(?:AI|artificial\s+intelligence|"
                         r"generative\s+AI|AI[- ]generat\w*)\b|"
                         r"(?iu)\b(?:штучн\w*\s+інтелект\w*|генеративн\w*\s+ШІ)\b")
_QUALIFIED = re.compile(r"(?i)\b(?:may|might|could|possibly|likely|suggests?|"
                        r"hypothesis|hypothesiz\w*|believ\w*)\b|"
                        r"(?iu)\b(?:мож\w*|ймовірн\w*|припуска\w*|гіпотез\w*)\b")


@dataclass(frozen=True, slots=True)
class EditorialBlueprint:
    kind: str
    reader_question: str
    lead_task: str
    proof_order: str
    hard_boundary: str
    angle: str = ""

    def prompt_block(self, *, final: bool = False) -> str:
        phase = "ФІНАЛЬНА ПЕРЕВІРКА РЕДАКЦІЙНОГО ЗАДУМУ" if final else "РЕДАКЦІЙНИЙ ПЛАН ДО НАПИСАННЯ"
        angle = (
            "КУТ ВІДБОРУ (це НЕ факт; застосуй лише якщо SOURCE його підтримує): "
            + self.angle + "\n"
            if self.angle else ""
        )
        return (
            phase + " [2.2.50; тип: " + self.kind + "]\n"
            + "ПИТАННЯ ЧИТАЧА: " + self.reader_question + "\n"
            + "ЗАВДАННЯ ПЕРШОГО АБЗАЦУ: " + self.lead_task + "\n"
            + "ПОСЛІДОВНІСТЬ: " + self.proof_order + "\n"
            + "МЕЖА ДОСТОВІРНОСТІ: " + self.hard_boundary + "\n"
            + angle
            + "Перевір, чи фінальний пост виконав завдання ЧИТАЧА, а не лише "
              "перерахував деталі. Не вставляй цей план або службові заголовки в Telegram."
        )


def build_editorial_blueprint(
    article: Any,
    *,
    monitoring: bool = False,
    commercial: bool = False,
    science: bool = False,
    angle: str = "",
) -> EditorialBlueprint:
    """Select presentation from the actual source, never from a neighboring story.

    The channel role, not its numeric ID or name, controls the format.
    No new fact, inferred intent, consequence or source substitution is allowed.
    """
    title = _read(article, "title")
    raw = _read(article, "raw_text")
    src = (title + "\n" + raw)[:9000]
    normalized_angle = " ".join(str(angle or "").split())[:280] if not monitoring else ""

    if monitoring:
        if _SERVICE.search(src) and _CONTACT.search(raw):
            return EditorialBlueprint(
                "civic_service", "Хто може отримати допомогу, яку саме і як звернутися?",
                "Назви послугу, цільову групу і доступність тільки за першоджерелом.",
                "Кому → що надають → умови/формат → окремі читабельні рядки контактів. "
                "Без штучних абзаців, а для короткого повідомлення без зайвих списків.",
                "Дослівно зберігай справжні телефони, email, URL, години та умови; "
                "не додавай неозвучених критеріїв або обіцянок.",
            )
        if _CIVIC_CHANGE.search(src):
            return EditorialBlueprint(
                "civic_notice", "Що зміниться для людей і коли, якщо це повідомлено?",
                "Постав підтверджену дію чи зміну раніше за назви посад.",
                "Конкретна зміна → кому стосується → дата, місце, спосіб дії (лише якщо є в SOURCE).",
                "Не перетворюй пропозицію на чинне рішення, початок атаки на результат "
                "або загальний анонс на індивідуальну гарантію.",
            )
        return EditorialBlueprint(
            "civic_report", "Що достеменно сталося та що потрібно знати?",
            "Почни із підтвердженої завершеної події або фактичної дії джерела.",
            "Підтверджена подія → суттєві наслідки/умови → необхідний контекст.",
            "Без непідтверджених наслідків, паніки, здогадів і зайвих висновків.",
        )

    if commercial:
        if _CREATIVE.search(src) and _HAND_CRAFT.search(src) and _AI_MENTION.search(src):
            return EditorialBlueprint(
                "commercial_contrast", "Що саме незвичайного в кампанії та в чому її підтверджений контраст?",
                "Назви бренд, конкретний прийом і підтверджене зіставлення.",
                "Що зробили → як реалізували → який саме контраст описує SOURCE "
                "(якщо це авторська оцінка, атрибутуй її автору).",
                "Не приписуй бренду намір відповідати конкуренту або боротися з AI, "
                "якщо такого наміру прямо не підтвердили.",
                normalized_angle,
            )
        return EditorialBlueprint(
            "commercial_story", "Яка нова дія бренду, продукт або креативна механіка, і чому це цікаво?",
            "Почни із конкретної дії та незвичного прийому, а не списку знаменитостей.",
            "Бренд/кампанія → креативна або комерційна механіка → "
            "підтверджений результат чи контекст; якщо їх немає, не придумуй.",
            "Відрізняй задум бренду від оцінки журналіста, участь у фільмі від авторства.",
            normalized_angle,
        )

    if science:
        return EditorialBlueprint(
            "science_insight", "Що виявили й чому це може бути цікаво людині поза спеціальністю?",
            "Почни з перевіреного відкриття та його значення, якщо значення зазначене в SOURCE.",
            "Головний результат → як його встановили → підтверджені наслідки й межі висновків. "
            "Складні позначення залиш лише коли вони необхідні.",
            ("SOURCE містить припущення: залиш його умовним. " if _QUALIFIED.search(src) else "")
            + "Не замінюй 'можливо' на 'доведено', не домислюй ролі кілець/планет "
              "та не додавай застосування з власної уяви.",
            normalized_angle,
        )
    return EditorialBlueprint(
        "general_news", "Що сталося і навіщо читачеві про це знати?",
        "Почни з конкретного доведеного факту, не з вступу про тренд.",
        "Подія → пояснення → підтверджений результат/значення.",
        "Без нових учасників, причин і заяв про значення поза SOURCE.",
        normalized_angle,
    )
