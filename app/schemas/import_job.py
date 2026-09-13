from typing import Literal

from pydantic import BaseModel

ImportStatus = Literal["queued", "running", "cancelling", "completed", "failed", "cancelled", "interrupted"]
ImportStage = Literal["queued", "preparing", "scanning", "thumbnail", "preview", "committing", "completed", "failed", "cancelling", "cancelled", "interrupted"]


class ImportStats(BaseModel):
    root_dir: str
    scanned_files: int = 0
    added_count: int = 0
    existing_count: int = 0
    skipped_count: int = 0
    thumbnail_count: int = 0
    preview_count: int = 0
    preview_requested: bool = False


class ImportJobOut(BaseModel):
    id: str
    request_id: str | None = None
    options: dict
    status: ImportStatus
    stage: ImportStage
    message: str
    percent: int
    current: int
    total: int
    current_file: str | None
    stats: ImportStats
    error: str | None
    created_at: str
    updated_at: str
