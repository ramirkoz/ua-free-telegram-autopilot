"""2.2.28: source-led, narrowly targeted correction of a failed READY post.

A failed factual assertion must be fixed against original source, not rerun through
the entire selector as though this were a new story. This helper never makes a
publishing decision and cannot waive source verification.
"""
from __future__ import annotations

from typing import Any


_REPAIR_NOTES: dict[str, str] = {
    "MONITORING_SOURCE_POLARITY_FLIP":
        "Перевір заперечення. Не перетворюй спростування/заперечення на підтвердження.",
    "MONITORING_UNCERTAINTY_ESCALATION":
        "Віднови рівень певності з джерела. Припущення й попередні повідомлення не стають доведеними фактами.",
    "FACT_UNSUPPORTED_FATALITY_COUNT":
        "Не змінюй кількість загиблих: використовуй лише однозначно підтверджене джерелом число.",
    "FACT_UNSUPPORTED_RATE_MULTIPLIER":
        "Частка людей у відсотках не доводить кратність частоти дій кожної людини.",
    "EDITORIAL_MIN_TWO_SENTENCES":
        "Перевір повноту оригінального матеріалу. Не вигадуй друге речення лише для обсягу.",
}


def _read(row: Any, key: str) -> str:
    try:
        return str(row[key] or "")
    except (TypeError, IndexError, KeyError):
        return str(getattr(row, key, "") or "")


def focused_rewrite_instructions(row: Any) -> str:
    """Return bounded repair rules, only for documented previous QA failures.

    Never infer missing prior source facts and never accept blank prior drafts.
    """
    code = _read(row, "last_error_code")
    if code not in {"PREPUBLISH_SOURCE_SAFETY", "PREPUBLISH_QA"}:
        return ""
    prior_text = _read(row, "final_text").strip()
    if len(prior_text) < 80:
        return ""
    try:
        retries = int(_read(row, "retry_count") or "0")
    except ValueError:
        return ""
    if not 1 <= retries <= 3:
        return ""
    detail = _read(row, "last_error_detail")[:700]
    fixes = [instruction for key, instruction in _REPAIR_NOTES.items() if key in detail]
    if not fixes:
        fixes = ["Виправ лише конкретну якісну помилку. Не змінюй достовірні факти й структуру без потреби."]
    return (
        "ПОВТОРНИЙ ФІНАЛЬНИЙ QA: попередній пост не пройшов обов'язкову перевірку. "
        "Перепиши ТІЛЬКИ помилкові фрагменти за оригінальним SOURCE, "
        "не запускаючи вибір новини заново. Коди минулої помилки: "
        + ", ".join(k for k in _REPAIR_NOTES if k in detail)[:250]
        + "\nКорекція: " + " ".join(fixes)
        + "\nНІКОЛИ не послаблюй джерельну перевірку і не перетворюй спростування на факт."
    )
