"""API-level tests for POST /api/v1/llm/generate.

Uses a fake in-memory LLMProvider injected via FastAPI dependency
overrides, so these tests exercise routing/validation/error-mapping
without touching HTTP or Ollama at all.
"""

from typing import Any

from fastapi.testclient import TestClient

from app.api.deps import get_llm_provider
from app.core.exceptions import ServiceUnavailableError
from app.llm.base import LLMProvider
from app.main import app


class FakeProvider(LLMProvider):
    def __init__(self, response_text: str = "fake response", model: str = "fake-model") -> None:
        self._response_text = response_text
        self._model = model

    @property
    def model_name(self) -> str:
        return self._model

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        return self._response_text

    async def generate_structured(self, prompt: str, schema: type, **kwargs: Any) -> Any:
        raise NotImplementedError

    async def embed(self, text: str) -> list[float]:
        raise NotImplementedError


class FailingProvider(LLMProvider):
    @property
    def model_name(self) -> str:
        return "fake-model"

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        raise ServiceUnavailableError("Local LLM service is unreachable")

    async def generate_structured(self, prompt: str, schema: type, **kwargs: Any) -> Any:
        raise NotImplementedError

    async def embed(self, text: str) -> list[float]:
        raise NotImplementedError


client = TestClient(app)


def teardown_function() -> None:
    app.dependency_overrides.pop(get_llm_provider, None)


def test_generate_success() -> None:
    app.dependency_overrides[get_llm_provider] = lambda: FakeProvider(
        response_text="A pressure relief valve protects equipment.", model="qwen3:8b"
    )

    response = client.post("/api/v1/llm/generate", json={"prompt": "Explain a pressure relief valve."})

    assert response.status_code == 200
    body = response.json()
    assert body["text"] == "A pressure relief valve protects equipment."
    assert body["model"] == "qwen3:8b"


def test_generate_rejects_empty_prompt() -> None:
    app.dependency_overrides[get_llm_provider] = lambda: FakeProvider()

    response = client.post("/api/v1/llm/generate", json={"prompt": ""})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_generate_rejects_missing_prompt() -> None:
    app.dependency_overrides[get_llm_provider] = lambda: FakeProvider()

    response = client.post("/api/v1/llm/generate", json={})

    assert response.status_code == 422


def test_generate_provider_failure_returns_503() -> None:
    app.dependency_overrides[get_llm_provider] = lambda: FailingProvider()

    response = client.post("/api/v1/llm/generate", json={"prompt": "hello"})

    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "service_unavailable"
    assert "unreachable" in body["error"]["message"]
