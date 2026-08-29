"""Real end-to-end test against a locally running Ollama instance and
the configured embedding model.

Automatically skipped if Ollama isn't reachable, or if the configured
embedding model isn't installed — never required for the normal (unit)
test run, and never triggers a model download.
"""

import httpx
import pytest

from app.core.config import settings
from app.rag.embeddings import OllamaEmbeddingProvider


def _installed_model_names() -> list[str] | None:
    try:
        response = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=2.0)
        if response.status_code != 200:
            return None
        return [model.get("model", "") for model in response.json().get("models", [])]
    except httpx.HTTPError:
        return None


def _model_is_installed(model_name: str, installed: list[str]) -> bool:
    # Ollama appends an implicit ":latest" tag when a model is pulled
    # without one specified, so compare the base name before ':'.
    return any(m == model_name or m.split(":")[0] == model_name.split(":")[0] for m in installed)


_installed = _installed_model_names()
_skip_reason = (
    "Ollama is not reachable locally"
    if _installed is None
    else (None if _model_is_installed(settings.embedding_model, _installed) else
          f"Configured embedding model '{settings.embedding_model}' is not installed locally")
)

pytestmark = pytest.mark.skipif(_skip_reason is not None, reason=_skip_reason or "")


@pytest.mark.anyio
async def test_real_ollama_embed() -> None:
    provider = OllamaEmbeddingProvider(
        base_url=settings.ollama_base_url,
        model=settings.embedding_model,
        timeout_seconds=settings.ollama_timeout_seconds,
    )

    vectors = await provider.embed(["Pressure relief valves protect equipment from overpressure."])

    assert len(vectors) == 1
    assert len(vectors[0]) > 0
    assert all(isinstance(x, float) for x in vectors[0])


@pytest.mark.anyio
async def test_real_ollama_embed_batch() -> None:
    provider = OllamaEmbeddingProvider(
        base_url=settings.ollama_base_url,
        model=settings.embedding_model,
        timeout_seconds=settings.ollama_timeout_seconds,
    )

    vectors = await provider.embed(["first document chunk", "second document chunk"])

    assert len(vectors) == 2
    assert len(vectors[0]) == len(vectors[1])


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
