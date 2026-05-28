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

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Add root_dir column to existing databases
        try:
            await conn.execute(text("ALTER TABLE media ADD COLUMN root_dir VARCHAR(1024)"))
        except Exception:
            pass
        try:
            await conn.execute(text("ALTER TABLE media ADD COLUMN preview_path VARCHAR(1024)"))
        except Exception:
            pass
