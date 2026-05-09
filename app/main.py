from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.media import router as media_router
from app.core.config import settings
from app.core.database import create_tables


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(media_router)
