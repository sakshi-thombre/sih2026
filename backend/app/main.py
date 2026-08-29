from fastapi import FastAPI

from app.api.v1.router import router as v1_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging

configure_logging(settings.log_level)

app = FastAPI(title=settings.app_name, debug=settings.debug)

register_exception_handlers(app)
app.include_router(v1_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": f"{settings.app_name} API is running"}
