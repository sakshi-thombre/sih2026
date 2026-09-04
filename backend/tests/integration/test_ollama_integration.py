"""Real end-to-end test against a locally running Ollama instance.

Automatically skipped if Ollama isn't reachable — never required for
the normal (unit) test run.
"""

import httpx
import pytest

from app.core.config import settings
from app.llm.ollama import OllamaProvider


def _ollama_reachable() -> bool:
    try:
        response = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=2.0)
        return response.status_code == 200
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(not _ollama_reachable(), reason="Ollama is not reachable locally")


@pytest.mark.anyio
async def test_real_ollama_generate() -> None:
    provider = OllamaProvider(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
        timeout_seconds=settings.ollama_timeout_seconds,
    )

    text = await provider.generate("Reply with a single word: hello")

    assert isinstance(text, str)
    assert len(text) > 0


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
