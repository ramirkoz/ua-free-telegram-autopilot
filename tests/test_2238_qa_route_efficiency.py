"""Regression gates for QA-safe route efficiency in Autopilot 2.2.38."""
from __future__ import annotations

from telegram_autopilot.v2.provider_api import ProviderAPIError
from telegram_autopilot.v2.ai_gateway import _rc111_qa_signature
from telegram_autopilot.v2.qa_route_efficiency_238 import (
    clipped_final_clause,
    conservative_completed_tail,
    suppress_reasoning_only_route,
    bounded_local_timeout,
)

BODY = (
    "Міська рада оприлюднила графік роботи сервісного центру. "
    "У повідомленні зазначено, що громадяни можуть подати заяву "
    "особисто протягом визначеного робочого часу. "
    "Організатори попросили відвідувачів перевіряти оголошення "
    "на офіційній сторінці громади."
)


def test_conservative_cut_drops_only_short_unfinished_final_fragment():
    original = BODY + " Додаткова інформація повідомляє, що"
    result = conservative_completed_tail(
        original, ValueError("Редакційний QA: незавершене речення або обірваний текст")
    )
    assert result == BODY
    assert result.endswith(".")
    assert "Додаткова інформація" not in result


def test_non_truncation_factual_safety_never_enters_repair_path():
    text = BODY + " Незаконний факт без перевірки"
    assert conservative_completed_tail(text, ValueError("AI додав число, якого немає у джерелі: 12")) == ""
    assert conservative_completed_tail(text, ValueError("MONITORING_SOURCE_POLARITY_FLIP")) == ""
    assert conservative_completed_tail(text, ValueError("Readability QA: зависока середня довжина речення")) == ""
    assert not clipped_final_clause(ValueError("AI додав дату, якої немає у джерелі"))


def test_trimming_refuses_long_or_unverified_clauses():
    assert conservative_completed_tail(BODY + " " + "неперевірений " * 30, ValueError(
        "Редакційний QA: незавершене речення або обірваний текст"
    )) == ""
    assert conservative_completed_tail("Перша подія. Друга", ValueError(
        "Редакційний QA: незавершене речення або обірваний текст"
    )) == ""
    assert conservative_completed_tail(BODY + " Подробиці: https://example.org/route", ValueError(
        "Редакційний QA: незавершене речення або обірваний текст"
    )) == ""


def test_trim_does_not_add_period_to_incomplete_user_facts():
    text = BODY + " Повідомляється про 123 постраждалих"
    repaired = conservative_completed_tail(text, ValueError(
        "Редакційний QA: незавершене речення або обірваний текст"
    ))
    assert repaired == BODY
    assert "123" not in repaired
    assert not repaired.endswith("постраждалих.")


def test_reasoning_only_task_suppression_is_provider_and_failure_scoped():
    mismatch = ProviderAPIError(
        "Provider returned reasoning but no final content; completion budget/format is incompatible",
        kind="bad_response",
    )
    assert suppress_reasoning_only_route("cloudflare", mismatch)
    assert not suppress_reasoning_only_route("groq", mismatch)
    assert not suppress_reasoning_only_route("cloudflare", ProviderAPIError("HTTP 429", kind="temporary"))
    assert not suppress_reasoning_only_route("cloudflare", ValueError("the model is unavailable"))


def test_local_cpu_fallback_timeout_is_bounded_without_changing_probe_timeouts():
    assert bounded_local_timeout(300, caller_timeout=25) == 120
    assert bounded_local_timeout(120, caller_timeout=20) == 120
    assert bounded_local_timeout(90, caller_timeout=90) == 90
    assert bounded_local_timeout(300, caller_timeout=200) == 300


def test_two_unrecoverable_truncated_routes_are_same_deterministic_qa_class():
    a = ValueError("Редакційний QA: незавершене речення або обірваний текст")
    b = ValueError("Останнє речення обірване")
    assert _rc111_qa_signature(a) == "truncated_tail"
    assert _rc111_qa_signature(b) == "truncated_tail"
    assert _rc111_qa_signature(ValueError("MONITORING_SOURCE_POLARITY_FLIP")) == ""
