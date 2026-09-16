from __future__ import annotations

from telegram_autopilot.v2 import provider_api
from telegram_autopilot.v2.provider_api import ProviderAPIError
from telegram_autopilot.v2.semantic_dedupe import semantic_same_event


def test_groq_json_validate_failed_is_task_validation_not_model_failure():
    detail = (
        '{"error":{"message":"Failed to generate JSON. Please adjust your prompt.",'
        '"type":"invalid_request_error","code":"json_validate_failed",'
        '"failed_generation":"max completion tokens reached before generating a valid document"}}'
    )
    error = provider_api._classify_http(400, detail, {})
    assert error.kind == "validation"
    assert error.status == 400


def test_groq_json_gate_retries_same_model_with_realistic_budget(monkeypatch):
    calls = []

    def fake_request(url, *, method="POST", headers=None, payload=None, timeout_seconds=25):
        calls.append(dict(payload or {}))
        if len(calls) == 1:
            raise ProviderAPIError(
                "HTTP 400: provider failed structured JSON generation",
                kind="validation",
                status=400,
            )
        return 200, {}, {
            "model": payload["model"],
            "choices": [{"message": {"content": '{"decision":"PASS","reason":"ok"}'}}],
        }

    monkeypatch.setattr(provider_api, "_request_json", fake_request)
    reply = provider_api.openai_compatible_chat(
        "groq",
        model="openai/gpt-oss-120b",
        api_key="test-key",
        prompt='Return JSON with keys "decision" and "reason".',
        max_output_tokens=190,
        timeout_seconds=5,
        json_mode=True,
    )

    assert reply.model == "openai/gpt-oss-120b"
    assert len(calls) == 2
    assert calls[0]["max_completion_tokens"] >= 768
    assert calls[1]["max_completion_tokens"] >= 1536
    assert calls[0]["reasoning_effort"] == "none"
    assert calls[0]["temperature"] == 0.0
    assert calls[0]["response_format"] == {"type": "json_object"}
    assert "STRICT STRUCTURED OUTPUT CONTRACT" in calls[0]["messages"][0]["content"]


def _row(*, source_id: int, source_name: str, title: str, raw_text: str, final_text: str = ""):
    return {
        "id": source_id,
        "source_id": source_id,
        "source_name": source_name,
        "title": title,
        "raw_text": raw_text,
        "final_text": final_text,
        "source_url": f"https://example{source_id}.gov.ua/post/{source_id}",
        "canonical_source_url": "",
        "content_hash": f"hash-{source_id}",
    }


def test_cross_community_same_veteran_psychological_service_is_duplicate():
    semenivska = _row(
        source_id=101,
        source_name="Семенівська громада",
        title="Психологічна допомога для ветеранів, захисників, захисниць та членів їхніх сімей",
        raw_text=(
            "Семенівська громада нагадує, що ветерани, захисники, захисниці та члени їхніх сімей "
            "мають право на безоплатну кваліфіковану психологічну допомогу за державний кошт. "
            "Послуги надають спеціалізовані заклади та фахівці з офіційного реєстру Міністерства "
            "у справах ветеранів України. Скористатися підтримкою можуть учасники бойових дій, "
            "особи з інвалідністю внаслідок війни, учасники війни та члени сімей ветеранів і загиблих захисників."
        ),
        final_text=(
            "Ветерани війни та члени їхніх сімей можуть безоплатно отримати психологічну допомогу. "
            "Послугу надають фахівці й заклади з офіційного реєстру Міністерства у справах ветеранів України."
        ),
    )
    novenska = _row(
        source_id=202,
        source_name="Новенська громада",
        title="Як ветеранам війни та членам їхніх сімей отримати психологічну допомогу",
        raw_text=(
            "Новенська громада роз’яснює порядок отримання послуги з психологічної допомоги для ветеранів війни, "
            "членів їхніх сімей та інших визначених категорій осіб. Скористатися цією послугою можуть ті, хто "
            "потребує підтримки та фахової допомоги. Діють державні та регіональні механізми звернення до профільних "
            "фахівців і закладів, включених до офіційного реєстру Міністерства у справах ветеранів України."
        ),
        final_text=(
            "Ветерани війни, члени їхніх сімей та інші визначені категорії можуть отримати психологічну допомогу. "
            "Для цього потрібно звернутися до профільних фахівців або закладів з офіційного реєстру Міністерства у справах ветеранів України."
        ),
    )

    same, reason = semantic_same_event(novenska, semenivska)
    assert same is True
    assert "community" in reason


def test_two_different_community_services_are_not_collapsed():
    housing = _row(
        source_id=301,
        source_name="Березівська громада",
        title="Компенсація за житло для ветеранів війни",
        raw_text="Громада повідомляє про компенсацію вартості житла ветеранам та членам їхніх сімей за державною програмою.",
        final_text="Ветерани можуть подати документи на компенсацію вартості житла за державною програмою.",
    )
    psychology = _row(
        source_id=302,
        source_name="Новенська громада",
        title="Психологічна допомога для ветеранів війни",
        raw_text="Громада інформує про безоплатну психологічну допомогу ветеранам і членам їхніх сімей у профільних фахівців.",
        final_text="Ветерани можуть безоплатно звернутися до фахівців по психологічну допомогу.",
    )

    same, _reason = semantic_same_event(psychology, housing)
    assert same is False
