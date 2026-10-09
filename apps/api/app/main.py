from fastapi import FastAPI

from app.api.router import router
from app.core.config import Settings

settings = Settings()
app = FastAPI(title=settings.app_name, version="0.1.0")
app.include_router(router)
