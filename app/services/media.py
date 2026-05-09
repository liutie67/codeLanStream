import os
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.media import Media, MediaType
from app.schemas.media import FeedResponse, MediaOut
from app.services.thumbnail import generate_thumbnail


def _classify_media(ext: str) -> MediaType | None:
    ext = ext.lower()
    if ext in settings.supported_video_exts:
        return MediaType.VIDEO
    if ext in settings.supported_image_exts:
        return MediaType.IMAGE
    return None


async def scan_directory(dir_path: str, db: AsyncSession) -> int:
    count = 0
    path = Path(dir_path)
    for file in path.rglob("*"):
        if not file.is_file():
            continue
        media_type = _classify_media(file.suffix)
        if media_type is None:
            continue

        exists = await db.execute(
            select(Media).where(Media.file_path == str(file.resolve()))
        )
        if exists.scalar_one_or_none():
            continue

        stat = file.stat()
        media = Media(
            file_path=str(file.resolve()),
            media_type=media_type,
            size_bytes=stat.st_size,
            folder=str(file.parent),
        )
        db.add(media)
        await db.flush()
        if media_type == MediaType.VIDEO:
            media.thumbnail_path = generate_thumbnail(str(file.resolve()), media.id)
        count += 1

    await db.commit()
    return count


async def get_feed(
    db: AsyncSession,
    page: int = 1,
    page_size: int = settings.feed_page_size,
    media_type: MediaType | None = None,
    folder: str | None = None,
) -> FeedResponse:
    query = select(Media)
    count_query = select(func.count(Media.id))

    if media_type:
        query = query.where(Media.media_type == media_type)
        count_query = count_query.where(Media.media_type == media_type)
    if folder:
        query = query.where(Media.folder.contains(folder))
        count_query = count_query.where(Media.folder.contains(folder))

    total = (await db.execute(count_query)).scalar_one()
    offset = (page - 1) * page_size

    query = query.order_by(Media.created_at.desc()).offset(offset).limit(page_size + 1)
    rows = (await db.execute(query)).scalars().all()

    has_next = len(rows) > page_size
    items = [MediaOut.model_validate(m) for m in rows[:page_size]]

    return FeedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_next=has_next,
    )


async def get_media(db: AsyncSession, media_id: str) -> Media | None:
    result = await db.execute(select(Media).where(Media.id == media_id))
    return result.scalar_one_or_none()


def parse_range(range_header: str, file_size: int) -> tuple[int, int]:
    """Parse Range header, return (start, end) bytes inclusive."""
    unit, ranges = range_header.split("=")
    if unit.strip() != "bytes":
        raise ValueError("Only bytes range is supported")

    part = ranges.split(",")[0].strip()
    start_str, end_str = part.split("-")

    if start_str == "" and end_str == "":
        raise ValueError("Invalid range")

    if start_str == "":
        start = file_size - int(end_str)
        end = file_size - 1
    elif end_str == "":
        start = int(start_str)
        end = file_size - 1
    else:
        start = int(start_str)
        end = min(int(end_str), file_size - 1)

    if start > end or start >= file_size:
        raise ValueError("Range not satisfiable")

    return start, end


def get_mime_type(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    mime_map = {
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mkv": "video/x-matroska",
        ".avi": "video/x-msvideo",
        ".mov": "video/quicktime",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }
    return mime_map.get(ext, "application/octet-stream")
