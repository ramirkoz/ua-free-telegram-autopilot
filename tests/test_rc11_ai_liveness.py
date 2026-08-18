from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from telegram_autopilot import ai_router
from telegram_autopilot.ai_router import AIRouterError, Slot
from telegram_autopilot.database import Database
from telegram_autopilot.secrets_store import SecretConfig


def _patch_state_path(monkeypatch, tmp_path):
    path = tmp_path / 'ai_router_state.json'
    monkeypatch.setattr(ai_router, 'ai_state_path', lambda: path)
    return path


def test_clear_router_cooldowns_can_clear_one_provider_or_all(monkeypatch, tmp_path):
    path = _patch_state_path(monkeypatch, tmp_path)
    path.write_text(json.dumps({
        'cooldowns': {
            'provider:groq': {'until': 9999999999, 'reason': 'quota'},
            'model:groq:m1': {'until': 9999999999, 'reason': 'bad'},
            'provider:nvidia': {'until': 9999999999, 'reason': 'quota'},
        }
    }), encoding='utf-8')

    ai_router.clear_router_cooldowns('groq')
    state = json.loads(path.read_text(encoding='utf-8'))
    assert 'provider:groq' not in state['cooldowns']
    assert 'model:groq:m1' not in state['cooldowns']
    assert 'provider:nvidia' in state['cooldowns']

    ai_router.clear_router_cooldowns()
    state = json.loads(path.read_text(encoding='utf-8'))
    assert state['cooldowns'] == {}


def test_local_failure_enters_short_cooldown_and_does_not_block_next_article(monkeypatch, tmp_path):
    path = _patch_state_path(monkeypatch, tmp_path)
    monkeypatch.setattr(ai_router, 'MODEL_SLOTS', (Slot(1, 'local', 'local-model', 'Local', 'local'),))
    monkeypatch.setattr(ai_router, 'load_secrets', lambda: SecretConfig(local_enabled=True))

    calls = {'count': 0}
    def fail_local(**kwargs):
        calls['count'] += 1
        raise ai_router.LocalAIRuntimeError('local unavailable')
    monkeypatch.setattr(ai_router, 'generate_local_text', fail_local)

    with pytest.raises(AIRouterError, match='Усі доступні AI-моделі'):
        ai_router.run_ai('test', task_timeout_seconds=30, local_timeout_seconds=2)
    assert calls['count'] == 1
    state = json.loads(path.read_text(encoding='utf-8'))
    assert 'provider:local' in state['cooldowns']

    with pytest.raises(AIRouterError, match='Немає доступного AI-провайдера'):
        ai_router.run_ai('test', task_timeout_seconds=30, local_timeout_seconds=2)
    assert calls['count'] == 1


def test_successful_router_diagnostic_clears_stale_provider_cooldown(monkeypatch, tmp_path):
    path = _patch_state_path(monkeypatch, tmp_path)
    path.write_text(json.dumps({
        'cooldowns': {'provider:local': {'until': 9999999999, 'reason': 'old failure'}}
    }), encoding='utf-8')
    monkeypatch.setattr(ai_router, 'MODEL_SLOTS', (Slot(1, 'local', 'local-model', 'Local', 'local'),))
    monkeypatch.setattr(ai_router, 'load_secrets', lambda: SecretConfig(local_enabled=True))
    monkeypatch.setattr(
        ai_router,
        'test_local_runtime',
        lambda **kwargs: SimpleNamespace(label='Ollama / qwen'),
    )

    rows = ai_router.test_all()
    assert rows == [('local', '✓', 'працює · Ollama / qwen')]
    state = json.loads(path.read_text(encoding='utf-8'))
    assert 'provider:local' not in state['cooldowns']


def test_rc11_service_resets_stale_cooldowns_once(monkeypatch, tmp_path):
    import telegram_autopilot.service as service_module

    db = Database(tmp_path / 'autopilot.sqlite3')
    calls = {'count': 0}
    monkeypatch.setattr(service_module, 'clear_router_cooldowns', lambda: calls.__setitem__('count', calls['count'] + 1))

    service_module.AutopilotService(db)
    service_module.AutopilotService(db)

    assert calls['count'] == 1
    assert db.get_state('rc11_ai_liveness_migrated') == '1'
