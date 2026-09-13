from typing import Any

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.media import Base


class ImportJob(Base):
    __tablename__ = "import_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    request_id: Mapped[str | None] = mapped_column(String(36), unique=True)
    # SQLite permits multiple NULLs, but only one active slot.
    active_slot: Mapped[str | None] = mapped_column(String(16), unique=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
