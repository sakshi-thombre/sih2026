"""Development/test endpoint for the local LLM. Not the final agent API."""

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user, get_llm_provider
from app.llm.base import LLMProvider
from app.schemas.llm import GenerateRequest, GenerateResponse
from app.services.llm_service import generate_text

router = APIRouter()


@router.post("/llm/generate", response_model=GenerateResponse)
async def generate(
    request: GenerateRequest,
    user: dict[str, str] = Depends(get_current_user),
    provider: LLMProvider = Depends(get_llm_provider),
) -> GenerateResponse:
    return await generate_text(provider, request.prompt)
