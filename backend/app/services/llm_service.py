"""Service layer for LLM interactions.

Routes call this instead of talking to an `LLMProvider` directly, so
provider-specific concerns stay out of `api/` and any future
pre/post-processing (e.g. prompt templating) has one place to live.
"""

from app.llm.base import LLMProvider
from app.schemas.llm import GenerateResponse


async def generate_text(provider: LLMProvider, prompt: str) -> GenerateResponse:
    text = await provider.generate(prompt)
    return GenerateResponse(text=text, model=provider.model_name)
