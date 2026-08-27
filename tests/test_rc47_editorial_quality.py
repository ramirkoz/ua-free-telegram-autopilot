from __future__ import annotations

from types import SimpleNamespace

import pytest

from telegram_autopilot.ai_router import AIRouterError, Result
from telegram_autopilot import rc45_policy as rc45
from telegram_autopilot import rc47_policy as rc47


def _channel():
    return SimpleNamespace(
        id=1,
        name="CTRL+UA",
        editorial_profile="Technology, AI, science, cybersecurity and infrastructure news. No generic politics or healthcare policy.",
        editorial_weights_json="[]",
        min_publish_interval_minutes=10,
        content_direction="en_to_uk",
    )


def _article(title="A real AI platform update", raw="A company released a concrete AI platform update with new capabilities."):
    return {
        "id": 4701,
        "title": title,
        "raw_text": raw,
        "source_published_at": "2026-08-27T08:00:00Z",
    }


def _categories():
    return [
        {"name": "AI Models & Agents", "weight": 60},
        {"name": "Cybersecurity & Privacy", "weight": 40},
    ]


def test_rc47_lowercase_or_clipped_start_is_blocked():
    issues = rc47._deterministic_editorial_blockers("ові пригоди знову вперлися в залізо. Далі є нормальний текст.")
    assert any("обрізаного" in issue for issue in issues)


def test_rc47_article_meta_framing_is_blocked():
    issues = rc47._deterministic_editorial_blockers(
        "STAT+ подає це як авторську колонку. Далі текст лише натякає на проблему."
    )
    assert any("статтю/видання" in issue for issue in issues)


def test_rc47_teaser_without_payload_is_blocked():
    issues = rc47._deterministic_editorial_blockers(
        "У законопроєкті є лазівка. Вона може послабити його ефект для галузі."
    )
    assert any("тизер" in issue for issue in issues)


def test_rc47_number_dump_is_blocked():
    issues = rc47._deterministic_editorial_blockers(
        "Компанія показала 96 млрд, +106%, +18%, має 279 млрд зобов'язань, 160 млрд на пам'ять, очікує 108 млрд, а прогноз дає ще 2%."
    )
    assert any("перевантажений числами" in issue for issue in issues)


def test_rc47_normal_editorial_body_has_no_deterministic_blocker():
    body = (
        "Nvidia вперлася не в попит на AI-прискорювачі, а в можливості ланцюга постачання. "
        "Компанія вже резервує пам'ять і виробничі потужності на майбутні покоління обладнання.\n\n"
        "Це означає, що головним обмеженням для подальшого росту стає фізична доступність компонентів, а не кількість замовлень."
    )
    assert rc47._deterministic_editorial_blockers(body) == ()


def test_rc47_unclassified_cheap_classifier_gets_trusted_retry(monkeypatch):
    monkeypatch.setattr(rc47, "_CHEAP_CLASSIFIER", lambda *_a, **_k: rc47._UNCLASSIFIED)
    monkeypatch.setattr(rc45, "lexical_category", lambda *_a, **_k: "")
    seen = {}

    def fake_run_ai(prompt, validator=None, **kwargs):
        seen.update(kwargs)
        result = Result("AI Models & Agents", "codex", "codex-chatgpt", "Codex", ("Codex",))
        if validator:
            validator(result.text)
        return result

    monkeypatch.setattr(rc47, "run_ai", fake_run_ai)
    category = rc47.classify_category_rc47(_channel(), _article(), _categories())
    assert category == "AI Models & Agents"
    assert seen["allowed_providers"] == {"codex", "gemini"}
    assert "local" in seen["skip_providers"]


def test_rc47_unclassified_and_trusted_failure_holds_for_retry(monkeypatch):
    monkeypatch.setattr(rc47, "_CHEAP_CLASSIFIER", lambda *_a, **_k: rc47._UNCLASSIFIED)
    monkeypatch.setattr(rc45, "lexical_category", lambda *_a, **_k: "")
    monkeypatch.setattr(rc47, "run_ai", lambda *_a, **_k: (_ for _ in ()).throw(AIRouterError("provider down")))
    with pytest.raises(AIRouterError, match="held for retry"):
        rc47.classify_category_rc47(_channel(), _article(), _categories())


def test_rc47_lexical_match_is_still_confirmed_by_trusted_editor(monkeypatch):
    monkeypatch.setattr(rc47, "_CHEAP_CLASSIFIER", lambda *_a, **_k: "AI Models & Agents")
    monkeypatch.setattr(rc45, "lexical_category", lambda *_a, **_k: "AI Models & Agents")
    calls = {"n": 0}

    def fake_run_ai(prompt, validator=None, **kwargs):
        calls["n"] += 1
        result = Result("__OTHER__", "gemini", "gemini-3.5-flash", "Gemini", ("Gemini",))
        if validator:
            validator(result.text)
        return result

    monkeypatch.setattr(rc47, "run_ai", fake_run_ai)
    category = rc47.classify_category_rc47(
        _channel(),
        _article(title="Hospital lobbying plan uses AI buzzword", raw="A healthcare lobbying story with an AI mention."),
        _categories(),
    )
    assert category == "__OTHER__"
    assert calls["n"] == 1


def test_rc47_prompts_require_self_contained_payload():
    prompt = rc47._final_editor_prompt(_channel(), _article(), "Чернетка.", hard_limit=900)
    assert "самодостатній" in prompt.casefold()
    assert "лазівка" in prompt.casefold()
    assert "конкретно поясни" in rc47._UA_EDITOR_ADDENDUM.casefold()
