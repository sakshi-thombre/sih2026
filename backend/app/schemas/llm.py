"""Request/response schemas for the development LLM test endpoint."""

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=8000)


class GenerateResponse(BaseModel):
    text: str
    model: str
