from __future__ import annotations

import json
import socket
import threading
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


class OllamaError(RuntimeError):
    pass


class OllamaTimeoutError(OllamaError):
    pass


def _model_key(value: str) -> str:
    name = str(value or "").strip()
    return name[:-7] if name.casefold().endswith(":latest") else name


_OLLAMA_OPERATION_LOCK = threading.RLock()


def _strip_code_fence(value: str) -> str:
    text = str(value or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


class OllamaClient:
    """Small local Ollama client reused from the stable Content Creator design.

    Local model operations are serialized so a preload and a generation do not fight
    over RAM/CPU on a small Windows machine. The client never installs Ollama and
    never downloads a model.
    """

    def __init__(self, base_url: str, timeout: int = 120, load_timeout: int = 90):
        self.base_url = str(base_url or "").rstrip("/")
        self.timeout = max(20, int(timeout))
        self.load_timeout = max(20, int(load_timeout))
        parts = urlsplit(self.base_url)
        if parts.scheme != "http" or parts.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise OllamaError("Ollama має використовувати локальну loopback HTTP-адресу.")

    def _request(self, path: str, payload: dict[str, object] | None = None) -> dict[str, object]:
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            self.base_url + path,
            data=data,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="GET" if payload is None else "POST",
        )
        try:
            with urlopen(request, timeout=min(self.load_timeout, 20)) as response:
                body = response.read(8 * 1024 * 1024)
        except HTTPError as exc:
            raise OllamaError(f"Ollama повернула HTTP {exc.code}.") from exc
        except (URLError, TimeoutError, socket.timeout) as exc:
            raise OllamaError("Ollama не відповідає або не запущена локально.") from exc
        try:
            result = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OllamaError("Ollama повернула некоректний JSON.") from exc
        if not isinstance(result, dict):
            raise OllamaError("Відповідь Ollama повинна бути JSON-об'єктом.")
        if result.get("error"):
            raise OllamaError(str(result["error"]))
        return result

    def list_models(self) -> list[str]:
        payload = self._request("/api/tags")
        models = payload.get("models", [])
        if not isinstance(models, list):
            return []
        return [str(item.get("name")) for item in models if isinstance(item, dict) and item.get("name")]

    def list_running_models(self) -> list[str]:
        payload = self._request("/api/ps")
        models = payload.get("models", [])
        if not isinstance(models, list):
            return []
        result: list[str] = []
        for item in models:
            if not isinstance(item, dict):
                continue
            value = item.get("name") or item.get("model")
            if value:
                result.append(str(value))
        return result

    def is_model_loaded(self, model: str) -> bool:
        wanted = _model_key(model)
        if not wanted:
            return False
        try:
            return any(_model_key(item) == wanted for item in self.list_running_models())
        except OllamaError:
            return False

    def preload_model(self, model: str) -> None:
        model = str(model or "").strip()
        if not model:
            raise OllamaError("Не знайдено встановлену модель Ollama.")
        with _OLLAMA_OPERATION_LOCK:
            if self.is_model_loaded(model):
                return
            payload = {
                "model": model,
                "prompt": "",
                "stream": False,
                "think": False,
                "keep_alive": "30m",
                "options": {"num_ctx": 2048, "num_predict": 1},
            }
            request = Request(
                self.base_url + "/api/generate",
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                method="POST",
            )
            try:
                with urlopen(request, timeout=self.load_timeout) as response:
                    body = response.read(2 * 1024 * 1024)
            except HTTPError as exc:
                raise OllamaError(f"Ollama не завантажила модель «{model}»: HTTP {exc.code}.") from exc
            except (URLError, TimeoutError, socket.timeout) as exc:
                raise OllamaTimeoutError(
                    f"Модель «{model}» не завантажилася за {self.load_timeout} секунд."
                ) from exc
            try:
                result = json.loads(body.decode("utf-8")) if body else {}
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise OllamaError("Ollama повернула некоректну відповідь під час завантаження моделі.") from exc
            if isinstance(result, dict) and result.get("error"):
                raise OllamaError(str(result["error"]))

    def generate_text(
        self,
        model: str,
        prompt: str,
        *,
        num_predict: int = 512,
        temperature: float = 0.05,
    ) -> str:
        if not model:
            raise OllamaError("Не знайдено встановлену модель Ollama.")
        with _OLLAMA_OPERATION_LOCK:
            self.preload_model(model)
            prompt_len = len(str(prompt or ""))
            if prompt_len <= 4_000:
                context_window = 2048
            elif prompt_len <= 9_000:
                context_window = 3072
            else:
                context_window = 4096
            payload = {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "think": False,
                "keep_alive": "30m",
                "options": {
                    "temperature": float(temperature),
                    "top_p": 0.9,
                    "repeat_penalty": 1.04,
                    "num_ctx": context_window,
                    "num_predict": max(32, int(num_predict)),
                },
            }
            request = Request(
                self.base_url + "/api/generate",
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                method="POST",
            )
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    body = response.read(8 * 1024 * 1024)
            except HTTPError as exc:
                raise OllamaError(f"Ollama повернула HTTP {exc.code}.") from exc
            except (URLError, TimeoutError, socket.timeout) as exc:
                raise OllamaTimeoutError(
                    f"Ollama не завершила локальне AI-завдання за {self.timeout} секунд."
                ) from exc
            try:
                result = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise OllamaError("Ollama повернула некоректний JSON-конверт.") from exc
            if not isinstance(result, dict):
                raise OllamaError("Відповідь Ollama повинна бути JSON-об'єктом.")
            if result.get("error"):
                raise OllamaError(str(result["error"]))
            return _strip_code_fence(str(result.get("response") or ""))
