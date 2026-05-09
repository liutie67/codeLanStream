from datetime import datetime

from pydantic import BaseModel

from app.models.media import MediaType


class MediaOut(BaseModel):
    id: str
    file_path: str
    media_type: MediaType
    size_bytes: int
    duration: float | None
    width: int | None
    height: int | None
    folder: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class FeedResponse(BaseModel):
    items: list[MediaOut]
    total: int
    page: int
    page_size: int
    has_next: bool
