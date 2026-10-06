from typing import Any

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.media import Base


class AvailabilityJob(Base):
    __tablename__ = "availability_check_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    active_slot: Mapped[str | None] = mapped_column(String(16), unique=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
