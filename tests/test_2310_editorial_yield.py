"""Regressions: human feedback, source rescue budget and model circuit."""
from telegram_autopilot.v2.editorial_feedback_2310 import calibrated_feedback_2310
from telegram_autopilot.v2.ai_route_circuit_263 import RouteContractCircuit


def test_role_scoped_feedback():
    assert "дослідження" in calibrated_feedback_2310("science")
    assert "типографіка" in calibrated_feedback_2310("creative")
    assert calibrated_feedback_2310("monitoring") == ""


def test_repeat_oversize_defers_only_groq_model():
    circuit = RouteContractCircuit()
    err = ValueError("HTTP 413: request too large")
    assert not circuit.note_failure("groq", "qwen", err, now=10)
    assert circuit.note_failure("groq", "qwen", err, now=20)
    assert circuit.remaining("groq", "qwen", now=30) > 0
    assert circuit.remaining("groq", "another", now=30) == 0
    assert circuit.remaining("gemini", "qwen", now=30) == 0
    assert circuit.remaining("groq", "qwen", now=321) == 0


def test_single_oversize_failure_does_not_cooldown():
    circuit = RouteContractCircuit()
    assert not circuit.note_failure("groq", "qwen", Exception("HTTP 413"), now=100)
    assert circuit.remaining("groq", "qwen", now=101) == 0


def test_unrelated_model_errors_not_circuited():
    circuit = RouteContractCircuit()
    assert not circuit.note_failure("gemini", "flash", ValueError("syntax invalid"), now=100)
    assert not circuit.note_failure("groq", "qwen", ValueError("HTTP 429 quota"), now=100)
