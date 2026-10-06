from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.media import router as media_router
from app.core.config import settings
from app.core.database import create_tables
from app.services.import_jobs import initialize_import_jobs, shutdown_import_jobs
from app.services.availability import initialize_availability, shutdown_availability
from app.services.availability_jobs import initialize_check_jobs, shutdown_check_jobs
from app.services.disk_probe import initialize_probes, shutdown_probes


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    initialize_probes()
    initialize_availability()
    await initialize_check_jobs()
    await initialize_import_jobs()
    try:
        yield
    finally:
        await shutdown_check_jobs()
        await shutdown_import_jobs()
        await shutdown_availability()
        await shutdown_probes()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(media_router)
