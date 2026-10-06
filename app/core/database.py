from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

engine = create_async_engine(settings.database_url, echo=settings.debug)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with async_session() as session:
        yield session


async def create_tables():
    from app.models.media import Base
    from app.models.import_job import ImportJob  # noqa: F401: register task table
    from app.models.availability_job import AvailabilityJob  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Inspect before altering: repeated startup is safe, real failures propagate.
        columns = {row[1] for row in (await conn.execute(text("PRAGMA table_info(media)"))).all()}
        additions = {
            "root_dir": "VARCHAR(1024)", "preview_path": "VARCHAR(1024)",
            "is_damaged": "BOOLEAN NOT NULL DEFAULT 0",
            "availability": "VARCHAR(16) NOT NULL DEFAULT 'available'",
            "availability_checked_at": "DATETIME",
        }
        for name, definition in additions.items():
            if name not in columns:
                await conn.execute(text(f"ALTER TABLE media ADD COLUMN {name} {definition}"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_media_availability ON media (availability)"))
