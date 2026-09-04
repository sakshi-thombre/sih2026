from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as v1_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging

configure_logging(settings.log_level)

app = FastAPI(title=settings.app_name, debug=settings.debug)

# Origins come from settings.cors_allow_origins (FRONTEND_ORIGINS in
# .env), never hardcoded here — see app/core/config.py. allow_credentials
# is True because the frontend sends the Supabase JWT via the
# Authorization header, which is why allow_origins can never be "*".
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)
app.include_router(v1_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": f"{settings.app_name} API is running"}
