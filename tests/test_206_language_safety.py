from __future__ import annotations

import json

import pytest

from telegram_autopilot import language_tool_local as lt
from telegram_autopilot.v2.editorial import _is_editorial_prompt_echo


class _Reply:
    status = 200

    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, *_):
        return json.dumps(self._payload).encode("utf-8")


@pytest.mark.parametrize("old,new", [
    ("ФПВ", "ТПВ"),
    ("ЗОВА", "МОВА"),
    ("вейп-шопів", "секс-шопів"),
    ("Семікін", "Семикін"),
    ("Наддніпрян'я", "Наддніпрянця"),
])
def test_morphological_correction_never_mutates_a_source_entity(monkeypatch, old, new):
    text = f"У повідомленні є {old} у Запоріжжі."
    result = _run_lt(monkeypatch, text, old, new, "misspelling", "MORFOLOGIK_RULE_UK_UA")
    assert result.text == text
    assert result.changes == 0


def _run_lt(monkeypatch, text, old, new, issue_type, rule_id):
    offset = text.index(old)
    payload = {"matches": [{
        "offset": offset,
        "length": len(old),
        "replacements": [{"value": new}],
        "rule": {"id": rule_id, "issueType": issue_type},
    }]}
    monkeypatch.setattr(lt, "_probe_server", lambda **_: True)
    monkeypatch.setattr(lt.urllib.request, "urlopen", lambda *_args, **_kwargs: _Reply(payload))
    monkeypatch.setattr(lt, "_record_check", lambda *_args, **_kwargs: None)
    return lt.apply_local_languagetool_detailed(text, source_text=text)


def test_grammar_word_replacement_cannot_mutate_fact(monkeypatch):
    text = "Удар завдав ФПВ-дрон."
    result = _run_lt(monkeypatch, text, "ФПВ", "ТПВ", "grammar", "RULE_X")
    assert result.text == text
    assert result.changes == 0


def test_punctuation_only_correction_remains_available(monkeypatch):
    text = "Подія сталася вчора , подробиці є."
    result = _run_lt(monkeypatch, text, "вчора ,", "вчора,", "typographical", "PUNCT")
    assert result.text == "Подія сталася вчора, подробиці є."
    assert result.changes == 1


@pytest.mark.parametrize("bad", [
    "Поверни ТІЛЬКИ готовий текст поста без службових пояснень.",
    "**Поверни ТІЛЬКИ готовий текст поста без службових пояснень.**",
    "Поверни тільки фінальний текст.",
])
def test_prompt_echo_rejected(bad):
    assert _is_editorial_prompt_echo(bad)


@pytest.mark.parametrize("valid", [
    "Мешканцям повернули світло після ремонту.",
    "**Увага:** у місті відкрили новий молодіжний центр.",
    "Повернули знайдені речі власникам.",
])
def test_real_news_and_markdown_not_rejected(valid):
    assert not _is_editorial_prompt_echo(valid)
