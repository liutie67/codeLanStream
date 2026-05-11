import os
import shutil
from pathlib import Path

from sqlalchemy import delete as sql_delete, func, select
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
    path = Path(dir_path).resolve()
    root = str(path)
    for file in path.rglob("*"):
        if not file.is_file():
            continue
        # Skip hidden files and files in hidden directories
        if any(part.startswith('.') for part in file.relative_to(path).parts):
            continue
        # Skip common system files
        if file.name in ('Thumbs.db', 'desktop.ini', 'Desktop.ini'):
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
            root_dir=root,
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
    is_favorited: bool | None = None,
    is_deleted: bool | None = None,
) -> FeedResponse:
    query = select(Media)
    count_query = select(func.count(Media.id))

    if media_type:
        query = query.where(Media.media_type == media_type)
        count_query = count_query.where(Media.media_type == media_type)
    if folder:
        query = query.where(Media.folder.contains(folder))
        count_query = count_query.where(Media.folder.contains(folder))
    if is_favorited is not None:
        query = query.where(Media.is_favorited == is_favorited)
        count_query = count_query.where(Media.is_favorited == is_favorited)
    if is_deleted is not None:
        query = query.where(Media.is_deleted == is_deleted)
        count_query = count_query.where(Media.is_deleted == is_deleted)

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


async def get_random_media(
    db: AsyncSession,
    count: int = 50,
    exclude_ids: list[str] | None = None,
    media_type: MediaType | None = None,
) -> dict:
    query = select(Media)
    count_query = select(func.count(Media.id))

    if media_type:
        query = query.where(Media.media_type == media_type)
        count_query = count_query.where(Media.media_type == media_type)

    if exclude_ids:
        query = query.where(Media.id.notin_(exclude_ids))

    query = query.order_by(func.random()).limit(count)

    result = await db.execute(query)
    items = [MediaOut.model_validate(m) for m in result.scalars().all()]

    total = (await db.execute(count_query)).scalar_one()

    return {"items": items, "total": total}


async def browse_folders(
    db: AsyncSession,
    root_dir: str | None = None,
    subdir: str | None = None,
    media_type: MediaType | None = None,
) -> dict:
    if root_dir is None:
        result = await db.execute(
            select(Media.root_dir, func.count(Media.id))
            .where(Media.root_dir.isnot(None))
            .group_by(Media.root_dir)
        )
        roots = [
            {"path": r, "name": Path(r).name, "count": c}
            for r, c in result.all()
        ]
        return {"roots": roots, "folders": [], "items": []}

    target_dir = str(Path(root_dir) / subdir) if subdir else root_dir

    # Media directly in this directory, sorted by filename
    query = select(Media).where(Media.folder == target_dir)
    if media_type:
        query = query.where(Media.media_type == media_type)
    query = query.order_by(Media.file_path)
    direct_result = await db.execute(query)
    items = [MediaOut.model_validate(m) for m in direct_result.scalars().all()]

    # Find immediate subdirectories
    sep = os.sep
    prefix = target_dir + sep
    sub_result = await db.execute(
        select(Media.folder)
        .where(Media.root_dir == root_dir, Media.folder.startswith(prefix))
        .distinct()
    )
    subdirs = sorted({
        folder[len(prefix):].split(sep)[0]
        for (folder,) in sub_result.all()
    })

    return {"roots": [], "folders": subdirs, "items": items}


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


async def toggle_favorite(db: AsyncSession, media_id: str) -> MediaOut:
    media = await get_media(db, media_id)
    if not media:
        raise ValueError("Media not found")
    media.is_favorited = not media.is_favorited
    await db.commit()
    await db.refresh(media)
    return MediaOut.model_validate(media)


async def toggle_deleted(db: AsyncSession, media_id: str) -> MediaOut:
    media = await get_media(db, media_id)
    if not media:
        raise ValueError("Media not found")
    media.is_deleted = not media.is_deleted
    await db.commit()
    await db.refresh(media)
    return MediaOut.model_validate(media)


async def purge_deleted(db: AsyncSession) -> int:
    result = await db.execute(select(Media).where(Media.is_deleted == True))
    items = result.scalars().all()
    count = 0
    for media in items:
        if media.file_path and os.path.exists(media.file_path):
            os.remove(media.file_path)
        if media.thumbnail_path and os.path.exists(media.thumbnail_path):
            os.remove(media.thumbnail_path)
        await db.delete(media)
        count += 1
    await db.commit()
    return count


async def export_favorites(db: AsyncSession, target_dir: str) -> int:
    result = await db.execute(select(Media).where(Media.is_favorited == True))
    items = result.scalars().all()
    Path(target_dir).mkdir(parents=True, exist_ok=True)
    count = 0
    for media in items:
        if media.file_path and os.path.exists(media.file_path):
            dest = Path(target_dir) / Path(media.file_path).name
            shutil.copy2(media.file_path, dest)
            count += 1
    return count


async def batch_update(db: AsyncSession, ids: list[str], action: str) -> int:
    count = 0
    for mid in ids:
        media = await get_media(db, mid)
        if not media:
            continue
        if action == "favorite":
            media.is_favorited = True
        elif action == "unfavorite":
            media.is_favorited = False
        elif action == "delete":
            media.is_deleted = True
        elif action == "undelete":
            media.is_deleted = False
        else:
            continue
        count += 1
    await db.commit()
    return count
