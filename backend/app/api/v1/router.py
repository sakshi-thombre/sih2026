from fastapi import APIRouter

from app.api.v1.endpoints import agent, documents, health, llm

router = APIRouter(prefix="/api/v1")
router.include_router(health.router, tags=["health"])
router.include_router(llm.router, tags=["llm"])
router.include_router(documents.router, tags=["documents"])
router.include_router(agent.router, tags=["agent"])
