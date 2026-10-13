from fastapi import FastAPI

from app.api.router import router
from app.core.config import Settings
from app.core.exceptions import register_exception_handlers

settings = Settings()
app = FastAPI(title=settings.app_name, version="0.1.0")
register_exception_handlers(app)
app.include_router(router)
